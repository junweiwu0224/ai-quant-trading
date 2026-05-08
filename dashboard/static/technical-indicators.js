/**
 * 技术指标计算引擎
 * 输入 K 线数据 [{date, open, close, high, low, volume}, ...]
 * 输出各指标数据，用于 LightweightCharts 渲染
 */
const TechnicalIndicators = {

    // ── 辅助函数 ──

    /** EMA（指数移动平均） */
    EMA(data, period) {
        if (data.length < period) return [];
        const k = 2 / (period + 1);
        const result = [];
        // 前 period 个用 SMA
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            result.push(data[i] * k + result[result.length - 1] * (1 - k));
        }
        return result;
    },

    /** SMA（简单移动平均） */
    SMA(data, period) {
        if (data.length < period) return [];
        const result = [];
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result.push(sum / period);
        }
        return result;
    },

    // ── MACD ──

    /**
     * MACD 指标
     * @param {number[]} closes - 收盘价数组
     * @param {number} fast - 快线周期（默认12）
     * @param {number} slow - 慢线周期（默认26）
     * @param {number} signal - 信号线周期（默认9）
     * @returns {{ dif: number[], dea: number[], macd: number[], dates: string[] }}
     */
    MACD(closes, dates, fast = 12, slow = 26, signal = 9) {
        if (closes.length < slow + signal) return null;

        const emaFast = this.EMA(closes, fast);
        const emaSlow = this.EMA(closes, slow);

        // 对齐：emaFast 从 index=fast-1 开始，emaSlow 从 index=slow-1 开始
        const slowOffset = slow - fast;
        const difRaw = [];
        for (let i = 0; i < emaSlow.length; i++) {
            difRaw.push(emaFast[i + slowOffset] - emaSlow[i]);
        }

        const deaRaw = this.EMA(difRaw, signal);
        const signalOffset = signal - 1;
        const dif = [];
        const dea = [];
        const macd = [];
        const resultDates = [];

        for (let i = 0; i < deaRaw.length; i++) {
            const difIdx = i + signalOffset;
            if (difIdx < difRaw.length) {
                dif.push(difRaw[difIdx]);
                dea.push(deaRaw[i]);
                macd.push((difRaw[difIdx] - deaRaw[i]) * 2);
                resultDates.push(dates[slow - 1 + difIdx]);
            }
        }

        return { dif, dea, macd, dates: resultDates };
    },

    // ── KDJ ──

    /**
     * KDJ 指标
     * @param {number[]} highs
     * @param {number[]} lows
     * @param {number[]} closes
     * @param {string[]} dates
     * @param {number} period - RSV周期（默认9）
     * @returns {{ k: number[], d: number[], j: number[], dates: string[] }}
     */
    KDJ(highs, lows, closes, dates, period = 9) {
        if (closes.length < period) return null;

        const rsv = [];
        for (let i = period - 1; i < closes.length; i++) {
            let highMax = -Infinity, lowMin = Infinity;
            for (let j = i - period + 1; j <= i; j++) {
                highMax = Math.max(highMax, highs[j]);
                lowMin = Math.min(lowMin, lows[j]);
            }
            const range = highMax - lowMin;
            rsv.push(range === 0 ? 50 : ((closes[i] - lowMin) / range) * 100);
        }

        const k = [], d = [], j = [];
        const resultDates = [];

        // 初始值 K=50, D=50
        let prevK = 50, prevD = 50;
        for (let i = 0; i < rsv.length; i++) {
            const curK = (2 / 3) * prevK + (1 / 3) * rsv[i];
            const curD = (2 / 3) * prevD + (1 / 3) * curK;
            const curJ = 3 * curK - 2 * curD;

            k.push(parseFloat(curK.toFixed(2)));
            d.push(parseFloat(curD.toFixed(2)));
            j.push(parseFloat(curJ.toFixed(2)));
            resultDates.push(dates[period - 1 + i]);

            prevK = curK;
            prevD = curD;
        }

        return { k, d, j, dates: resultDates };
    },

    // ── RSI ──

    /**
     * RSI 相对强弱指标
     * @param {number[]} closes
     * @param {string[]} dates
     * @param {number} period - 周期（默认6, 14, 24）
     * @returns {{ rsi: number[], dates: string[] }}
     */
    RSI(closes, dates, period = 14) {
        if (closes.length < period + 1) return null;

        const gains = [], losses = [];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? -diff : 0);
        }

        const result = [];
        const resultDates = [];

        // 初始 SMA
        let avgGain = 0, avgLoss = 0;
        for (let i = 0; i < period; i++) {
            avgGain += gains[i];
            avgLoss += losses[i];
        }
        avgGain /= period;
        avgLoss /= period;

        const rs0 = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push(parseFloat((100 - 100 / (1 + rs0)).toFixed(2)));
        resultDates.push(dates[period]);

        // 后续用 EMA 方式
        for (let i = period; i < gains.length; i++) {
            avgGain = (avgGain * (period - 1) + gains[i]) / period;
            avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
            const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
            result.push(parseFloat((100 - 100 / (1 + rs)).toFixed(2)));
            resultDates.push(dates[i + 1]);
        }

        return { rsi: result, dates: resultDates };
    },

    // ── BOLL（布林带）──

    /**
     * BOLL 布林带
     * @param {number[]} closes
     * @param {string[]} dates
     * @param {number} period - 周期（默认20）
     * @param {number} multiplier - 标准差倍数（默认2）
     * @returns {{ upper: number[], middle: number[], lower: number[], dates: string[] }}
     */
    BOLL(closes, dates, period = 20, multiplier = 2) {
        if (closes.length < period) return null;

        const upper = [], middle = [], lower = [];
        const resultDates = [];

        for (let i = period - 1; i < closes.length; i++) {
            let sum = 0;
            for (let j = i - period + 1; j <= i; j++) sum += closes[j];
            const ma = sum / period;

            let variance = 0;
            for (let j = i - period + 1; j <= i; j++) {
                variance += (closes[j] - ma) ** 2;
            }
            const std = Math.sqrt(variance / period);

            middle.push(parseFloat(ma.toFixed(2)));
            upper.push(parseFloat((ma + multiplier * std).toFixed(2)));
            lower.push(parseFloat((ma - multiplier * std).toFixed(2)));
            resultDates.push(dates[i]);
        }

        return { upper, middle, lower, dates: resultDates };
    },

    // ── WR（威廉指标）──

    /**
     * WR 威廉指标
     * @param {number[]} highs
     * @param {number[]} lows
     * @param {number[]} closes
     * @param {string[]} dates
     * @param {number} period - 周期（默认14）
     * @returns {{ wr: number[], dates: string[] }}
     */
    WR(highs, lows, closes, dates, period = 14) {
        if (closes.length < period) return null;

        const wr = [];
        const resultDates = [];

        for (let i = period - 1; i < closes.length; i++) {
            let highMax = -Infinity, lowMin = Infinity;
            for (let j = i - period + 1; j <= i; j++) {
                highMax = Math.max(highMax, highs[j]);
                lowMin = Math.min(lowMin, lows[j]);
            }
            const range = highMax - lowMin;
            const val = range === 0 ? 50 : ((highMax - closes[i]) / range) * -100;
            wr.push(parseFloat(val.toFixed(2)));
            resultDates.push(dates[i]);
        }

        return { wr, dates: resultDates };
    },

    // ── OBV（能量潮）──

    /**
     * OBV 能量潮指标
     * @param {number[]} closes
     * @param {number[]} volumes
     * @param {string[]} dates
     * @returns {{ obv: number[], dates: string[] }}
     */
    OBV(closes, volumes, dates) {
        if (closes.length < 2) return null;

        const obv = [0];
        const resultDates = [dates[0]];

        for (let i = 1; i < closes.length; i++) {
            let val = obv[obv.length - 1];
            if (closes[i] > closes[i - 1]) {
                val += volumes[i];
            } else if (closes[i] < closes[i - 1]) {
                val -= volumes[i];
            }
            obv.push(val);
            resultDates.push(dates[i]);
        }

        return { obv, dates: resultDates };
    },

    // ── 批量计算 ──

    /**
     * 从 K 线数据计算指定指标
     * @param {Array} klines - [{date, open, close, high, low, volume}, ...]
     * @param {string} name - 指标名称
     * @returns {Object|null}
     */
    calculate(klines, name) {
        const closes = klines.map(k => k.close);
        const highs = klines.map(k => k.high);
        const lows = klines.map(k => k.low);
        const volumes = klines.map(k => k.volume);
        const dates = klines.map(k => k.date);

        switch (name.toUpperCase()) {
            case 'MACD': return this.MACD(closes, dates);
            case 'KDJ':  return this.KDJ(highs, lows, closes, dates);
            case 'RSI':  return this.RSI(closes, dates);
            case 'BOLL': return this.BOLL(closes, dates);
            case 'WR':   return this.WR(highs, lows, closes, dates);
            case 'OBV':  return this.OBV(closes, volumes, dates);
            default:     return null;
        }
    },
};
