/* ─── Spieltagsplaner – Client Logic ───────────────────────── */

(function () {
    'use strict';

    // ─── DOM refs ────────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const uploadZone = $('#uploadZone');
    const fileInput = $('#fileInput');
    const fileNameEl = $('#fileName');
    const btnStart = $('#btnStart');
    const btnBack = $('#btnBack');
    const stepUpload = $('#step-upload');
    const stepResults = $('#step-results');
    const loading = $('#loading');
    const toast = $('#toast');
    const statsRow = $('#statsRow');
    const gruppenContainer = $('#gruppenContainer');
    const filterAk = $('#filterAk');
    const filterSk = $('#filterSk');
    const btnExpandAll = $('#btnExpandAll');
    const btnCollapseAll = $('#btnCollapseAll');
    const resetSettings = $('#resetSettings');
    const mapGruppeFilter = $('#mapGruppeFilter');

    // Map
    let map = null;
    let mapLayers = [];

    // Sliders
    const sliders = {
        wDistanz: { el: $('#wDistanz'), valEl: $('#wDistanzVal') },
        wRegion:  { el: $('#wRegion'),  valEl: $('#wRegionVal') },
        wBalance: { el: $('#wBalance'), valEl: $('#wBalanceVal') },
        maxSize:  { el: $('#maxSize'),  valEl: $('#maxSizeVal') },
    };

    let selectedFile = null;
    let resultData = null;

    // ─── Tab Switching ───────────────────────────────────────
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const panel = document.getElementById('tab-' + btn.dataset.tab);
            if (panel) panel.classList.add('active');
        });
    });

    // ─── Upload Zone ─────────────────────────────────────────
    uploadZone.addEventListener('click', () => fileInput.click());

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            handleFile(fileInput.files[0]);
        }
    });

    function handleFile(file) {
        if (!file.name.match(/\.xlsx?$/i)) {
            showToast('Nur Excel-Dateien (.xlsx) erlaubt', 'error');
            return;
        }
        selectedFile = file;
        fileNameEl.textContent = file.name;
        fileNameEl.style.display = 'block';
        btnStart.disabled = false;
    }

    // ─── Sliders ─────────────────────────────────────────────
    Object.values(sliders).forEach(({ el, valEl }) => {
        el.addEventListener('input', () => {
            valEl.textContent = el.value;
        });
    });

    resetSettings.addEventListener('click', () => {
        sliders.wDistanz.el.value = '1.0'; sliders.wDistanz.valEl.textContent = '1.0';
        sliders.wRegion.el.value = '50'; sliders.wRegion.valEl.textContent = '50';
        sliders.wBalance.el.value = '20'; sliders.wBalance.valEl.textContent = '20';
        sliders.maxSize.el.value = '11'; sliders.maxSize.valEl.textContent = '11';
    });

    // ─── Start Button ────────────────────────────────────────
    btnStart.addEventListener('click', async () => {
        if (!selectedFile) return;

        loading.style.display = 'flex';

        const formData = new FormData();
        formData.append('file', selectedFile);

        const params = new URLSearchParams({
            w_distanz: sliders.wDistanz.el.value,
            w_region: sliders.wRegion.el.value,
            w_balance: sliders.wBalance.el.value,
            max_staffel_size: sliders.maxSize.el.value,
        });

        try {
            const resp = await fetch(`/api/einteilung?${params}`, {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Server-Fehler');
            }

            resultData = await resp.json();
            renderResults(resultData);
            stepUpload.style.display = 'none';
            stepResults.style.display = 'block';
            showToast('Einteilung berechnet!', 'success');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            loading.style.display = 'none';
        }
    });

    // ─── Back Button ─────────────────────────────────────────
    btnBack.addEventListener('click', () => {
        stepResults.style.display = 'none';
        stepUpload.style.display = 'block';
        resultData = null;
    });

    // ─── Render Results ──────────────────────────────────────
    function renderResults(data) {
        // Stats
        const totalStaffeln = data.gruppen.reduce((s, g) => s + g.staffeln.length, 0);
        const totalViolations = data.gruppen.reduce((s, g) => s + (g.score ? g.score.violations : 0), 0);
        const avgDist = data.gruppen
            .filter(g => g.score)
            .reduce((s, g) => s + g.score.distanz, 0) / Math.max(1, data.gruppen.filter(g => g.score).length);

        statsRow.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${data.total_teams}</div>
                <div class="stat-label">Mannschaften</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${totalStaffeln}</div>
                <div class="stat-label">Staffeln</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${data.teams_mit_coords}</div>
                <div class="stat-label">mit Koordinaten</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: ${totalViolations > 0 ? 'var(--danger)' : 'var(--success)'}">
                    ${totalViolations}
                </div>
                <div class="stat-label">Violations</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${avgDist.toFixed(1)}</div>
                <div class="stat-label">Ø Distanz (km)</div>
            </div>
        `;

        // Filters
        const altersklassen = [...new Set(data.gruppen.map(g => g.altersklasse))].sort();
        const spielklassen = [...new Set(data.gruppen.map(g => g.spielklasse))].sort();

        filterAk.innerHTML = '<option value="">Alle Altersklassen</option>' +
            altersklassen.map(ak => `<option value="${ak}">${ak}</option>`).join('');
        filterSk.innerHTML = '<option value="">Alle Spielklassen</option>' +
            spielklassen.map(sk => `<option value="${sk}">${sk}</option>`).join('');

        renderGruppen(data.gruppen);

        // Reset map filter and render map
        mapGruppeFilter.innerHTML = '<option value="">Alle Gruppen</option>';
        setTimeout(() => renderMap(data), 200);
    }

    function renderGruppen(gruppen) {
        const akFilter = filterAk.value;
        const skFilter = filterSk.value;

        const filtered = gruppen.filter(g => {
            if (akFilter && g.altersklasse !== akFilter) return false;
            if (skFilter && g.spielklasse !== skFilter) return false;
            return true;
        });

        if (filtered.length === 0) {
            gruppenContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--text-light)" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    </div>
                    <p>Keine Gruppen gefunden.</p>
                </div>
            `;
            return;
        }

        gruppenContainer.innerHTML = filtered.map((g, gi) => {
            const topfBadge = g.topf === 'fix'
                ? '<span class="gruppe-badge badge-gray">Regionenstaffel</span>'
                : g.topf === 'Topf 1'
                    ? '<span class="gruppe-badge badge-green">Topf 1</span>'
                    : '<span class="gruppe-badge badge-gold">Topf 2</span>';

            const violBadge = g.score && g.score.violations > 0
                ? `<span class="gruppe-badge badge-red">${g.score.violations} Violations</span>`
                : '';

            const scoreInfo = g.score
                ? `<span>Score: ${g.score.total}</span><span>Ø ${g.score.distanz} km</span>`
                : '';

            const staffelnHtml = g.staffeln.map((s, si) => renderStaffel(s, si)).join('');

            return `
                <div class="gruppe" data-index="${gi}">
                    <div class="gruppe-header" onclick="toggleGruppe(this)">
                        <div class="gruppe-title">
                            <span>${g.altersklasse}</span>
                            ${topfBadge}
                            ${violBadge}
                            <span style="color: var(--text-muted); font-weight: 400; font-size: 0.85rem;">
                                ${g.n_teams} Teams · ${g.staffeln.length} Staffel${g.staffeln.length !== 1 ? 'n' : ''}
                            </span>
                        </div>
                        <div class="gruppe-meta">
                            ${scoreInfo}
                            <span class="gruppe-chevron">▼</span>
                        </div>
                    </div>
                    <div class="gruppe-body">
                        ${staffelnHtml}
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderStaffel(staffel, index) {
        const dr = staffel.doppelrunde ? '<span class="gruppe-badge badge-gold">Doppelrunde</span>' : '';
        const sizes = `${staffel.n_teams} Teams`;
        const maxDist = staffel.max_distanz_km > 0
            ? `Max. ${staffel.max_distanz_km} km`
            : '';

        // Region counts
        const regionCounts = {};
        staffel.teams.forEach(t => {
            regionCounts[t.region] = (regionCounts[t.region] || 0) + 1;
        });
        const regionStr = Object.entries(regionCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([r, n]) => `${r}: ${n}`)
            .join(' · ');

        const rows = staffel.teams.map(t => {
            const dotClass = t.region === 'Hohenlohe' ? 'hohenlohe'
                : t.region === 'Unterland' ? 'unterland'
                : 'unknown';
            const ort = t.adresse ? t.adresse.split(', ').pop() : '';
            return `
                <tr>
                    <td>${t.mannschaft}</td>
                    <td><span class="region-dot ${dotClass}"></span>${t.region}</td>
                    <td>${ort}</td>
                </tr>
            `;
        }).join('');

        return `
            <div class="staffel">
                <div class="staffel-header">
                    <div class="staffel-name">
                        Staffel ${index + 1} ${dr}
                    </div>
                    <div class="staffel-info">
                        <span>${sizes}</span>
                        <span>${regionStr}</span>
                        <span>${maxDist}</span>
                    </div>
                </div>
                <table class="teams-table">
                    <thead>
                        <tr>
                            <th>Mannschaft</th>
                            <th>Region</th>
                            <th>Ort</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        `;
    }

    // ─── Filters ─────────────────────────────────────────────
    filterAk.addEventListener('change', () => resultData && renderGruppen(resultData.gruppen));
    filterSk.addEventListener('change', () => resultData && renderGruppen(resultData.gruppen));

    // ─── Map ─────────────────────────────────────────────────
    const STAFFEL_COLORS = [
        '#c41230', '#2563eb', '#059669', '#d97706', '#7c3aed',
        '#db2777', '#0891b2', '#65a30d', '#ea580c', '#4f46e5',
        '#0d9488', '#b91c1c', '#1d4ed8', '#15803d', '#a16207',
        '#6d28d9', '#be185d', '#0e7490', '#4d7c0f', '#c2410c',
    ];

    function initMap() {
        if (map) { map.invalidateSize(); return; }
        const mapEl = document.getElementById('map');
        if (!mapEl) return;

        map = L.map('map').setView([49.25, 9.7], 9);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap',
            maxZoom: 16,
        }).addTo(map);
    }

    function renderMap(data) {
        initMap();
        // Clear existing
        mapLayers.forEach(l => map.removeLayer(l));
        mapLayers = [];

        const gruppeFilter = mapGruppeFilter.value;
        const bounds = [];
        let staffelGlobalIdx = 0;

        // Populate map filter dropdown
        if (mapGruppeFilter.options.length <= 1) {
            data.gruppen.forEach((g, gi) => {
                const opt = document.createElement('option');
                opt.value = gi;
                opt.textContent = `${g.altersklasse} ${g.topf}`;
                mapGruppeFilter.appendChild(opt);
            });
        }

        data.gruppen.forEach((g, gi) => {
            if (gruppeFilter !== '' && String(gi) !== gruppeFilter) {
                staffelGlobalIdx += g.staffeln.length;
                return;
            }

            g.staffeln.forEach((staffel, si) => {
                const color = STAFFEL_COLORS[staffelGlobalIdx % STAFFEL_COLORS.length];
                staffelGlobalIdx++;

                const coords = [];
                staffel.teams.forEach(t => {
                    if (t.lat == null || t.lon == null) return;
                    coords.push([t.lat, t.lon]);

                    const marker = L.circleMarker([t.lat, t.lon], {
                        radius: 7,
                        fillColor: color,
                        color: '#fff',
                        weight: 2,
                        fillOpacity: 0.9,
                    }).addTo(map);

                    marker.bindPopup(
                        `<strong>${t.mannschaft}</strong><br>` +
                        `${t.region}<br>` +
                        `<small>${g.altersklasse} ${g.topf} – Staffel ${si + 1}</small>`
                    );

                    mapLayers.push(marker);
                    bounds.push([t.lat, t.lon]);
                });

                // Draw convex hull as polygon if 3+ points
                if (coords.length >= 3) {
                    const hull = convexHull(coords);
                    const poly = L.polygon(hull, {
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.08,
                        weight: 2,
                        dashArray: '4 4',
                    }).addTo(map);
                    mapLayers.push(poly);
                }
            });
        });

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    // Simple convex hull (Graham scan)
    function convexHull(points) {
        const pts = points.slice().sort((a, b) => a[1] - b[1] || a[0] - b[0]);
        if (pts.length <= 2) return pts;

        function cross(O, A, B) {
            return (A[1] - O[1]) * (B[0] - O[0]) - (A[0] - O[0]) * (B[1] - O[1]);
        }

        const lower = [];
        for (const p of pts) {
            while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0)
                lower.pop();
            lower.push(p);
        }

        const upper = [];
        for (const p of pts.reverse()) {
            while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0)
                upper.pop();
            upper.push(p);
        }

        upper.pop();
        lower.pop();
        return lower.concat(upper);
    }

    mapGruppeFilter.addEventListener('change', () => resultData && renderMap(resultData));

    // ─── Expand/Collapse ─────────────────────────────────────
    btnExpandAll.addEventListener('click', () => {
        document.querySelectorAll('.gruppe').forEach(g => g.classList.add('open'));
    });

    btnCollapseAll.addEventListener('click', () => {
        document.querySelectorAll('.gruppe').forEach(g => g.classList.remove('open'));
    });

    // ─── Toggle Gruppe (global) ──────────────────────────────
    window.toggleGruppe = function (header) {
        header.closest('.gruppe').classList.toggle('open');
    };

    // ─── Toast ───────────────────────────────────────────────
    function showToast(message, type = 'success') {
        toast.textContent = message;
        toast.className = `toast toast-${type} show`;
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }
})();
