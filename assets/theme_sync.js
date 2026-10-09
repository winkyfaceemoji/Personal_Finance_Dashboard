// Mirror #app-root's theme class (dark-theme / light-theme) onto <body>.
// Dash 4 renders dropdown popups in a portal directly under <body>, outside
// #app-root, so the theme tokens (--bg, --surface, --Dash-*, …) must be
// defined on <body> as well for those popups to pick them up.

document.body.className = 'dark-theme';  // before Dash renders: no white flash

function attachObserver() {
    var appRoot = document.getElementById('app-root');
    if (!appRoot) {
        setTimeout(attachObserver, 50);
        return;
    }
    document.body.className = appRoot.className;
    new MutationObserver(function () {
        document.body.className = appRoot.className;
    }).observe(appRoot, { attributes: true, attributeFilter: ['class'] });
}

attachObserver();
