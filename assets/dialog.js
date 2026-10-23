// The labeling panel is a full-screen dialog. Dash only toggles its
// display, so this script does the keyboard part (WCAG 2.4.3):
// - on open, focus moves into the panel;
// - Tab never leaves it (the page behind is covered);
// - Escape closes it, through DONE, so the close callback still runs;
// - on close, focus goes back to the button that opened it.

(function () {
    var opener = null;

    function panel() { return document.getElementById('label-panel'); }
    function isOpen(p) { return p && p.style.display !== 'none'; }

    function focusables(p) {
        return Array.prototype.filter.call(
            p.querySelectorAll('button, input, summary, [tabindex]:not([tabindex="-1"]), a[href]'),
            function (el) { return !el.disabled && el.getClientRects().length > 0; });
    }

    function attach() {
        var p = panel();
        if (!p) { setTimeout(attach, 50); return; }
        var wasOpen = isOpen(p);
        new MutationObserver(function () {
            var open = isOpen(p);
            if (open && !wasOpen) {
                opener = document.activeElement;
                p.focus();
            } else if (!open && wasOpen && opener && document.contains(opener)) {
                opener.focus();
                opener = null;
            }
            wasOpen = open;
        }).observe(p, { attributes: true, attributeFilter: ['style'] });
    }

    document.addEventListener('keydown', function (e) {
        var p = panel();
        if (!isOpen(p)) return;
        if (e.key === 'Escape') {
            // An open dropdown closes itself first; only the next Escape closes the panel
            if (document.querySelector('.dash-dropdown-content[data-state=open]')) return;
            var done = document.getElementById('close-label-panel');
            if (done) { e.preventDefault(); done.click(); }
        } else if (e.key === 'Tab') {
            var els = focusables(p);
            if (!els.length) return;
            var first = els[0], last = els[els.length - 1];
            var inside = p.contains(document.activeElement);
            if (e.shiftKey && (!inside || document.activeElement === first || document.activeElement === p)) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && (!inside || document.activeElement === last)) {
                e.preventDefault(); first.focus();
            }
        }
    }, true);   // capture: runs before the dropdown's own handler closes it

    attach();
})();
