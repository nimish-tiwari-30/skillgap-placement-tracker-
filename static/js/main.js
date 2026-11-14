/**
 * main.js — Skill Gap & Employment Outcome Tracking System
 * Modern Dashboard Utilities:
 * 1. Responsive mobile sidebar drawer toggle & outside-click close
 * 2. Double-submit prevention on forms with loading state
 * 3. Selective auto-dismiss for success alerts (errors remain open)
 * 4. Reusable delete confirmation modal helper
 */

document.addEventListener('DOMContentLoaded', function () {

    // ── 1. Responsive Sidebar Drawer Toggle ──────────────────────
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');

    if (toggle && sidebar) {
        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            sidebar.classList.toggle('sidebar-open');
        });

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', function (e) {
            if (window.innerWidth <= 992 && sidebar.classList.contains('sidebar-open')) {
                if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
                    sidebar.classList.remove('sidebar-open');
                }
            }
        });
    }

    // ── 2. Prevent Double Submit on Forms ────────────────────────
    const forms = document.querySelectorAll('form');
    forms.forEach(function (form) {
        form.addEventListener('submit', function (e) {
            // If native HTML5 validation fails, don't disable button
            if (!form.checkValidity()) {
                return;
            }

            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.classList.contains('no-disable')) {
                // Short timeout to let the submit event cycle initiate
                setTimeout(function () {
                    submitBtn.disabled = true;
                    submitBtn.classList.add('btn-loading');
                }, 20);
            }
        });
    });

    // ── 3. Auto-Dismiss Flash Messages (Success ONLY) ────────────
    // Error, danger, and warning alerts stay open until manually dismissed
    const successAlerts = document.querySelectorAll('.alert-success.alert-dismissible');
    successAlerts.forEach(function (alert) {
        setTimeout(function () {
            try {
                if (window.bootstrap && bootstrap.Alert) {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    if (bsAlert) bsAlert.close();
                } else {
                    alert.style.display = 'none';
                }
            } catch (err) {
                alert.style.display = 'none';
            }
        }, 5000);
    });

    // ── 4. Live Navbar Clock ─────────────────────────────────────
    const clockEl = document.getElementById('currentTime');
    if (clockEl) {
        function updateClock() {
            const now = new Date();
            clockEl.textContent = now.toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', hour12: true
            });
        }
        updateClock();
        setInterval(updateClock, 1000);
    }

    // ── 5. Destructive Action Confirmation Modal Helper ──────────
    // Any button or form with [data-confirm] triggers a standardized modal
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            const message = el.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
            if (!window.confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    });

});
