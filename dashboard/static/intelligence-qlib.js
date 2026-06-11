/* Legacy intelligence qlib shim: keep old URLs from overriding Signal Engine UI. */
(function () {
    'use strict';

    const app = globalThis.App;
    if (app && typeof app.loadBundleForPage === 'function') {
        app.loadBundleForPage?.('signals');
    }
})();
