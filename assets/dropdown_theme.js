// Theming for Dash 4 dropdowns.
// Dash 4 uses CSS variables (--Dash-*) defined on :root.
// We override them on document.documentElement via inline style so they beat
// any CSS rule (inline styles > stylesheets) and cascade to ALL children —
// including Radix portal content rendered directly inside <body>.

var DARK_VARS = {
    '--Dash-Fill-Inverse-Strong': '#111318',
    '--Dash-Stroke-Strong':       '#252830',
    '--Dash-Stroke-Weak':         'rgba(255,255,255,0.05)',
    '--Dash-Text-Primary':        '#ffffff',
    '--Dash-Text-Strong':         '#ffffff',
    '--Dash-Text-Weak':           '#c8cadb',
    '--Dash-Text-Disabled':       '#8a8fa8',
    '--Dash-Fill-Interactive-Strong': '#6c8aff',
    '--Dash-Fill-Interactive-Weak':   'rgba(108,138,255,0.15)',
    '--Dash-Fill-Primary-Hover':  '#252830',
    '--Dash-Fill-Primary-Active': '#2a2e3a',
    '--Dash-Fill-Disabled':       '#252830',
    '--Dash-Shading-Strong':      'rgba(0,0,0,0.5)',
    '--Dash-Shading-Weak':        'rgba(0,0,0,0.3)'
};

var LIGHT_VARS = {
    '--Dash-Fill-Inverse-Strong': '#f0f1f5',
    '--Dash-Stroke-Strong':       '#dcdee8',
    '--Dash-Stroke-Weak':         'rgba(0,0,0,0.05)',
    '--Dash-Text-Primary':        '#0a0a0f',
    '--Dash-Text-Strong':         '#0a0a0f',
    '--Dash-Text-Weak':           '#5c5f72',
    '--Dash-Text-Disabled':       '#5c5f72',
    '--Dash-Fill-Interactive-Strong': '#4a68e8',
    '--Dash-Fill-Interactive-Weak':   'rgba(74,104,232,0.1)',
    '--Dash-Fill-Primary-Hover':  '#dcdee8',
    '--Dash-Fill-Primary-Active': '#d0d2e0',
    '--Dash-Fill-Disabled':       '#dcdee8',
    '--Dash-Shading-Strong':      'rgba(0,0,0,0.2)',
    '--Dash-Shading-Weak':        'rgba(0,0,0,0.1)'
};

function applyTheme(themeClass) {
    var vars = themeClass === 'dark-theme' ? DARK_VARS : LIGHT_VARS;
    var root = document.documentElement;
    Object.keys(vars).forEach(function(k) {
        root.style.setProperty(k, vars[k]);
    });
    // Also set body class so our class-based CSS (cards, tabs, etc.) works
    document.body.className = themeClass || '';
}

// Apply dark theme immediately — before Dash JS even runs
applyTheme('dark-theme');

// Once React has rendered #app-root, sync its class and watch for changes
function attachObserver() {
    var appRoot = document.getElementById('app-root');
    if (!appRoot) {
        setTimeout(attachObserver, 50);
        return;
    }
    // Sync current class (may differ if user had light theme last session)
    applyTheme(appRoot.className);

    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            if (m.attributeName === 'class') {
                applyTheme(m.target.className);
            }
        });
    });
    observer.observe(appRoot, { attributes: true });
}

attachObserver();
