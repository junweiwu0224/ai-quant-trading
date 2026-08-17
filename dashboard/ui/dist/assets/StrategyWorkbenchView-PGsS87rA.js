import{B as b}from"./BaseCard-C3__eT5k.js";import{B as C}from"./BaseButton-B3vILJ_b.js";import{B as x}from"./BaseTag-DjWlr3bW.js";import{B as p}from"./BaseInput-BtsAvxDV.js";import{y as Z,d as F,o as I,c as d,a as t,t as n,b as o,h as r,g as N,e as _,l as u,s as c,f as m,F as L,r as H,n as U,D as P}from"./index-DUlIBPRX.js";import{R as W}from"./refresh-cw-DBkh-ECH.js";import{C as q}from"./code-xml-s0jQM90U.js";import{P as E}from"./play-B46p7ffF.js";/**
 * @license lucide-vue-next v0.468.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=Z("FileCodeIcon",[["path",{d:"M10 12.5 8 15l2 2.5",key:"1tg20x"}],["path",{d:"m14 12.5 2 2.5-2 2.5",key:"yinavb"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z",key:"1mlx9k"}]]),O=[{id:"s1",name:"双均线策略",type:"momentum",description:"基于5日和20日均线的经典趋势跟踪策略",code:`# 双均线策略
def initialize(context):
    context.short_window = 5
    context.long_window = 20
    context.symbol = '000300.SH'

def handle_data(context, data):
    short_ma = data.history(context.symbol, 'close', context.short_window).mean()
    long_ma = data.history(context.symbol, 'close', context.long_window).mean()

    current_position = context.portfolio.positions.get(context.symbol, 0)

    if short_ma > long_ma and current_position == 0:
        order_target_percent(context.symbol, 1.0)
    elif short_ma < long_ma and current_position > 0:
        order_target_percent(context.symbol, 0)`,status:"active",created_at:"2024-01-15T00:00:00Z",updated_at:"2024-08-10T00:00:00Z",last_backtest:"2024-08-10T15:30:00Z"},{id:"s2",name:"均值回归策略",type:"mean_reversion",description:"基于布林带的均值回归策略",code:`# 布林带均值回归策略
def initialize(context):
    context.window = 20
    context.num_std = 2
    context.symbol = '000300.SH'

def handle_data(context, data):
    prices = data.history(context.symbol, 'close', context.window)
    mean = prices.mean()
    std = prices.std()

    upper_band = mean + context.num_std * std
    lower_band = mean - context.num_std * std
    current_price = data.current(context.symbol, 'close')

    if current_price < lower_band:
        order_target_percent(context.symbol, 1.0)
    elif current_price > upper_band:
        order_target_percent(context.symbol, 0)`,status:"active",created_at:"2024-02-01T00:00:00Z",updated_at:"2024-08-12T00:00:00Z",last_backtest:"2024-08-12T10:20:00Z"},{id:"s3",name:"RSI超买超卖",type:"mean_reversion",description:"基于RSI指标的反转策略",code:`# RSI策略
def initialize(context):
    context.rsi_period = 14
    context.oversold = 30
    context.overbought = 70
    context.symbol = '000300.SH'

def handle_data(context, data):
    rsi = calculate_rsi(data, context.symbol, context.rsi_period)
    current_position = context.portfolio.positions.get(context.symbol, 0)

    if rsi < context.oversold and current_position == 0:
        order_target_percent(context.symbol, 1.0)
    elif rsi > context.overbought and current_position > 0:
        order_target_percent(context.symbol, 0)`,status:"draft",created_at:"2024-03-10T00:00:00Z",updated_at:"2024-08-15T00:00:00Z"},{id:"s4",name:"多因子选股",type:"ml_based",description:"结合动量、价值、质量因子的机器学习选股策略",code:`# 多因子ML策略
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def initialize(context):
    context.model = RandomForestClassifier(n_estimators=100)
    context.factors = ['momentum_20d', 'pe_ratio', 'roe']
    context.rebalance_days = 20

def handle_data(context, data):
    if context.trading_day % context.rebalance_days != 0:
        return

    # 获取因子数据
    factor_data = get_factor_data(data, context.factors)

    # 预测
    predictions = context.model.predict_proba(factor_data)

    # 选择top 10股票
    top_stocks = predictions.argsort()[-10:]

    # 等权重配置
    for symbol in top_stocks:
        order_target_percent(symbol, 0.1)`,status:"draft",created_at:"2024-04-05T00:00:00Z",updated_at:"2024-08-16T00:00:00Z"},{id:"s5",name:"网格交易策略",type:"arbitrage",description:"在价格区间内设置网格，低买高卖",code:`# 网格交易策略
def initialize(context):
    context.symbol = '000300.SH'
    context.grid_size = 0.02  # 2%网格
    context.num_grids = 10
    context.base_price = None

def handle_data(context, data):
    current_price = data.current(context.symbol, 'close')

    if context.base_price is None:
        context.base_price = current_price

    # 计算当前所在网格
    price_change = (current_price - context.base_price) / context.base_price
    grid_level = int(price_change / context.grid_size)

    # 网格交易逻辑
    target_position = 0.5 - grid_level * 0.05
    target_position = max(0, min(1.0, target_position))

    order_target_percent(context.symbol, target_position)`,status:"archived",created_at:"2024-02-20T00:00:00Z",updated_at:"2024-07-30T00:00:00Z",last_backtest:"2024-07-30T14:00:00Z"}];new Date().toISOString();async function X(){return await new Promise(y=>setTimeout(y,500)),O}const $={class:"page-container"},j={class:"page-head"},A={class:"head-actions"},G={key:0,class:"error-banner"},J={key:1,class:"loading-state"},K={key:2,class:"content-layout"},Q={class:"sidebar"},Y={class:"strategy-list"},tt=["onClick"],et={class:"strategy-header"},at={class:"strategy-name"},st={class:"strategy-meta"},ot={class:"strategy-date"},nt={class:"main-area"},it={key:0,class:"main-content"},lt={class:"editor-header"},dt={class:"section-title"},rt={class:"editor-description"},ct={class:"editor-actions"},ut={class:"code-editor"},mt={class:"code-editor-toolbar"},pt={class:"toolbar-label"},_t={class:"code-content"},vt={class:"config-grid"},gt={class:"config-item"},ft={class:"config-item"},bt={class:"config-item"},xt={class:"config-item"},yt={class:"config-item"},ht={class:"config-actions"},kt={key:1,class:"no-selection"},wt={key:3,class:"empty-state"},zt="策略工作台",Vt="策略开发、回测与版本管理的集成环境",Ct=F({__name:"StrategyWorkbenchView",setup(y){const v=u(!1),g=u(null),f=u([]),l=u(null),i=u({startDate:"2023-01-01",endDate:"2024-08-17",initialCapital:1e6,commissionRate:3e-4,slippageRate:1e-4}),T=u(!1);async function h(){v.value=!0,g.value=null;try{const a=await X();f.value=a,a.length>0&&!l.value&&k(a[0])}catch(a){console.error("Failed to load strategies:",a),g.value="加载策略数据失败，请稍后重试"}finally{v.value=!1}}function k(a){l.value=a,T.value=!1}function R(a){return{momentum:"动量",mean_reversion:"均值回归",arbitrage:"套利",ml_based:"机器学习",custom:"自定义"}[a]||a}function B(a){return{momentum:"success",mean_reversion:"info",arbitrage:"warning",ml_based:"info",custom:"default"}[a]||"default"}function w(a){return{active:"success",draft:"warning",archived:"default"}[a]||"default"}function z(a){return{active:"运行中",draft:"草稿",archived:"已归档"}[a]||a}function D(a){return new Date(a).toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}function M(){alert(`回测执行功能开发中

提示：将支持参数优化、Walk-Forward验证等高级功能`)}return I(()=>{h()}),(a,e)=>(c(),d("div",$,[t("div",j,[t("div",null,[t("h1",null,n(zt)),t("p",null,n(Vt))]),t("div",A,[o(C,{variant:"ghost",size:"sm",loading:v.value,onClick:h},{default:r(()=>[o(_(W),{size:16}),e[5]||(e[5]=m(" 刷新 ",-1))]),_:1},8,["loading"])])]),g.value?(c(),d("div",G,n(g.value),1)):N("",!0),v.value&&f.value.length===0?(c(),d("div",J,[...e[6]||(e[6]=[t("div",{class:"spinner"},null,-1),t("p",null,"加载中...",-1)])])):f.value.length>0?(c(),d("div",K,[t("aside",Q,[o(b,{padding:"md"},{default:r(()=>[e[7]||(e[7]=t("h2",{class:"section-title"},"策略列表",-1)),t("div",Y,[(c(!0),d(L,null,H(f.value,s=>{var V;return c(),d("div",{key:s.id,class:U(["strategy-item",{selected:((V=l.value)==null?void 0:V.id)===s.id}]),onClick:St=>k(s)},[t("div",et,[o(_(S),{size:16,class:"strategy-icon"}),t("span",at,n(s.name),1)]),t("div",st,[o(x,{variant:B(s.type),size:"sm"},{default:r(()=>[m(n(R(s.type)),1)]),_:2},1032,["variant"]),o(x,{variant:w(s.status),size:"sm"},{default:r(()=>[m(n(z(s.status)),1)]),_:2},1032,["variant"])]),t("div",ot," 更新: "+n(D(s.updated_at)),1)],10,tt)}),128))])]),_:1})]),t("div",nt,[l.value?(c(),d("div",it,[o(b,{padding:"lg",class:"editor-card"},{default:r(()=>[t("div",lt,[t("div",null,[t("h2",dt,n(l.value.name),1),t("p",rt,n(l.value.description),1)]),t("div",ct,[o(x,{variant:w(l.value.status)},{default:r(()=>[m(n(z(l.value.status)),1)]),_:1},8,["variant"])])]),t("div",ut,[t("div",mt,[t("span",pt,[o(_(q),{size:14}),e[8]||(e[8]=m(" Python Strategy Code ",-1))]),e[9]||(e[9]=t("span",{class:"toolbar-hint"},"只读模式 - 完整编辑器功能开发中",-1))]),t("pre",_t,n(l.value.code),1)])]),_:1}),o(b,{padding:"lg",class:"config-card"},{default:r(()=>[e[16]||(e[16]=t("h2",{class:"section-title"},"回测配置",-1)),t("div",vt,[t("div",gt,[e[10]||(e[10]=t("label",null,"起始日期",-1)),o(p,{modelValue:i.value.startDate,"onUpdate:modelValue":e[0]||(e[0]=s=>i.value.startDate=s),type:"date",size:"md"},null,8,["modelValue"])]),t("div",ft,[e[11]||(e[11]=t("label",null,"结束日期",-1)),o(p,{modelValue:i.value.endDate,"onUpdate:modelValue":e[1]||(e[1]=s=>i.value.endDate=s),type:"date",size:"md"},null,8,["modelValue"])]),t("div",bt,[e[12]||(e[12]=t("label",null,"初始资金",-1)),o(p,{modelValue:i.value.initialCapital,"onUpdate:modelValue":e[2]||(e[2]=s=>i.value.initialCapital=s),type:"number",size:"md",placeholder:"1000000"},null,8,["modelValue"])]),t("div",xt,[e[13]||(e[13]=t("label",null,"手续费率",-1)),o(p,{modelValue:i.value.commissionRate,"onUpdate:modelValue":e[3]||(e[3]=s=>i.value.commissionRate=s),type:"number",step:"0.0001",size:"md",placeholder:"0.0003"},null,8,["modelValue"])]),t("div",yt,[e[14]||(e[14]=t("label",null,"滑点率",-1)),o(p,{modelValue:i.value.slippageRate,"onUpdate:modelValue":e[4]||(e[4]=s=>i.value.slippageRate=s),type:"number",step:"0.0001",size:"md",placeholder:"0.0001"},null,8,["modelValue"])])]),t("div",ht,[o(C,{variant:"primary",size:"md",disabled:!0,onClick:M},{default:r(()=>[o(_(E),{size:16}),e[15]||(e[15]=m(" 运行回测（功能开发中） ",-1))]),_:1})])]),_:1}),o(b,{padding:"lg",class:"results-card"},{default:r(()=>[...e[17]||(e[17]=[t("h2",{class:"section-title"},"回测结果",-1),t("div",{class:"results-placeholder"},[t("div",{class:"placeholder-chart"},[t("div",{class:"chart-icon"},"📈"),t("p",null,"权益曲线图表区域"),t("span",{class:"placeholder-hint"},"运行回测后显示策略表现曲线")]),t("div",{class:"metrics-preview"},[t("div",{class:"metric-card"},[t("div",{class:"metric-label"},"累计收益率"),t("div",{class:"metric-value placeholder-value"},"--")]),t("div",{class:"metric-card"},[t("div",{class:"metric-label"},"年化收益率"),t("div",{class:"metric-value placeholder-value"},"--")]),t("div",{class:"metric-card"},[t("div",{class:"metric-label"},"Sharpe比率"),t("div",{class:"metric-value placeholder-value"},"--")]),t("div",{class:"metric-card"},[t("div",{class:"metric-label"},"最大回撤"),t("div",{class:"metric-value placeholder-value"},"--")])])],-1)])]),_:1})])):(c(),d("div",kt,[o(_(S),{size:48,class:"no-selection-icon"}),e[18]||(e[18]=t("p",null,"请从左侧选择一个策略",-1))]))])])):(c(),d("div",wt," 暂无策略数据 "))]))}}),Nt=P(Ct,[["__scopeId","data-v-cd0d52dd"]]);export{Nt as default};
