/**
 * chart-theme.js — Shared Chart.js Palette & Configuration
 * Provides consistent styling, typography, responsive behavior,
 * and accessible light-theme visuals across student and admin dashboards.
 */

(function () {
    // Standard color palette for metrics & categories
    const ChartTheme = {
        primary: '#4f46e5',     // Indigo
        primaryLight: '#818cf8',
        primaryAlpha: 'rgba(79, 70, 229, 0.15)',

        secondary: '#06b6d4',   // Cyan / Teal
        secondaryAlpha: 'rgba(6, 182, 212, 0.15)',

        success: '#10b981',     // Emerald
        successAlpha: 'rgba(16, 185, 129, 0.15)',

        warning: '#f59e0b',     // Amber
        warningAlpha: 'rgba(245, 158, 11, 0.15)',

        danger: '#ef4444',      // Rose
        dangerAlpha: 'rgba(239, 68, 68, 0.15)',

        info: '#3b82f6',        // Blue
        infoAlpha: 'rgba(59, 130, 246, 0.15)',

        palette: [
            '#4f46e5', '#06b6d4', '#10b981', '#f59e0b',
            '#ec4899', '#8b5cf6', '#3b82f6', '#14b8a6',
            '#f97316', '#64748b'
        ],

        // Read CSS variable dynamically or fallback
        getCssVar: function (name, fallback) {
            try {
                const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
                return val || fallback;
            } catch (e) {
                return fallback;
            }
        },

        isDarkMode: function () {
            return false;
        },

        getTextColor: function () {
            return '#64748b';
        },

        getGridColor: function () {
            return 'rgba(0, 0, 0, 0.06)';
        },

        getCardBg: function () {
            return '#ffffff';
        },

        // Apply shared global Chart.js defaults if Chart is present
        applyDefaults: function () {
            if (typeof Chart === 'undefined') return;

            const textColor = this.getTextColor();
            const gridColor = this.getGridColor();

            Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            Chart.defaults.font.size = 12;
            Chart.defaults.color = textColor;
            Chart.defaults.responsive = true;
            Chart.defaults.maintainAspectRatio = false;

            // Plugins default styling
            if (Chart.defaults.plugins) {
                if (Chart.defaults.plugins.legend) {
                    Chart.defaults.plugins.legend.labels.color = textColor;
                    Chart.defaults.plugins.legend.labels.usePointStyle = true;
                    Chart.defaults.plugins.legend.labels.padding = 16;
                }
                if (Chart.defaults.plugins.tooltip) {
                    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.95)';
                    Chart.defaults.plugins.tooltip.titleColor = '#ffffff';
                    Chart.defaults.plugins.tooltip.bodyColor = '#e2e8f0';
                    Chart.defaults.plugins.tooltip.padding = 10;
                    Chart.defaults.plugins.tooltip.cornerRadius = 8;
                    Chart.defaults.plugins.tooltip.boxPadding = 6;
                }
            }

            // Scales default styling
            if (Chart.defaults.scales) {
                if (Chart.defaults.scales.linear) {
                    Chart.defaults.scales.linear.grid = { color: gridColor, drawBorder: false };
                    Chart.defaults.scales.linear.ticks = { color: textColor };
                }
                if (Chart.defaults.scales.category) {
                    Chart.defaults.scales.category.grid = { display: false };
                    Chart.defaults.scales.category.ticks = { color: textColor };
                }
            }
        }
    };

    // Expose globally
    window.ChartTheme = ChartTheme;

    // Apply defaults on initial page load if Chart exists
    if (typeof Chart !== 'undefined') {
        ChartTheme.applyDefaults();
    }
})();
