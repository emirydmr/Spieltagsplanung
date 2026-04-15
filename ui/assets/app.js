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
    const mapGruppeFilter = $('#mapGruppeFilter');
    const btnExport = $('#btnExport');

    // Map
    let map = null;
    let mapLayers = [];

    let selectedFile = null;
    let resultData = null;

    // Drag-and-drop state
    let dragTeam = null;   // { gruppeIdx, staffelIdx, teamIdx, data }
    let editGruppeIdx = null; // which gruppe is currently being edited

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

    // ─── Start Button ────────────────────────────────────────
    btnStart.addEventListener('click', async () => {
        if (!selectedFile) return;

        loading.style.display = 'flex';

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const resp = await fetch('/api/einteilung', {
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

    // ─── Excel Export ────────────────────────────────────────
    btnExport.addEventListener('click', async () => {
        if (!resultData) return;
        try {
            btnExport.disabled = true;
            btnExport.textContent = 'Exportiere...';
            const resp = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(resultData),
            });
            if (!resp.ok) throw new Error('Export fehlgeschlagen');
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'Staffeleinteilung.xlsx';
            a.click();
            URL.revokeObjectURL(url);
            showToast('Excel exportiert', 'success');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            btnExport.disabled = false;
            btnExport.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Excel Export';
        }
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
                <div class="stat-label">Teams</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${totalStaffeln}</div>
                <div class="stat-label">Staffeln</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${avgDist.toFixed(1)}</div>
                <div class="stat-label">Ø Distanz (km)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: ${totalViolations > 0 ? 'var(--danger)' : 'var(--success)'}">
                    ${totalViolations}
                </div>
                <div class="stat-label">Probleme</div>
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
                ? `<span class="gruppe-badge badge-red">${g.score.violations} Probleme</span>`
                : '';

            const scoreInfo = g.score
                ? `<span>Ø ${g.score.distanz} km</span>`
                : '';

            // Find the real index inside resultData.gruppen
            const realIdx = resultData.gruppen.indexOf(g);
            const staffelnHtml = g.staffeln.map((s, si) => renderStaffel(s, si, realIdx)).join('');

            const editBtn = g.staffeln.length > 1
                ? `<button class="btn btn-sm btn-secondary edit-gruppe-btn" data-gruppe="${realIdx}" onclick="event.stopPropagation(); window.openEditPanel(${realIdx})">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    Bearbeiten
                  </button>`
                : '';

            return `
                <div class="gruppe" data-index="${realIdx}">
                    <div class="gruppe-header" onclick="toggleGruppe(this)" data-real-idx="${realIdx}">
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
                            ${editBtn}
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

    function renderStaffel(staffel, staffelIdx, gruppeIdx) {
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

        const rows = staffel.teams.map((t, ti) => {
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
            <div class="staffel" data-gruppe="${gruppeIdx}" data-staffel="${staffelIdx}">
                <div class="staffel-header">
                    <div class="staffel-name">
                        Staffel ${staffelIdx + 1} ${dr}
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

    // ─── Toggle Gruppe (global) → also filter map ──────────
    window.toggleGruppe = function (header) {
        const gruppe = header.closest('.gruppe');
        gruppe.classList.toggle('open');

        // When opening a gruppe, filter map to show only that gruppe
        if (gruppe.classList.contains('open') && resultData) {
            const realIdx = header.dataset.realIdx;
            if (realIdx !== undefined) {
                mapGruppeFilter.value = realIdx;
                renderMap(resultData);
            }
        }
    };

    // ─── Edit Panel (reassign teams between staffeln) ────────
    window.openEditPanel = function (gruppeIdx) {
        editGruppeIdx = gruppeIdx;
        renderEditPanel();
    };

    function renderEditPanel() {
        if (editGruppeIdx == null || !resultData) return;

        const g = resultData.gruppen[editGruppeIdx];
        if (!g) return;

        // Build a flat list of all teams with their current staffel assignment
        const allTeams = [];
        g.staffeln.forEach((s, si) => {
            s.teams.forEach(t => {
                allTeams.push({ team: t, staffelIdx: si });
            });
        });
        allTeams.sort((a, b) => a.team.mannschaft.localeCompare(b.team.mannschaft));

        const staffelOptions = g.staffeln.map((s, si) =>
            `<option value="${si}">Staffel ${si + 1}</option>`
        ).join('');

        const rows = allTeams.map((item, idx) => {
            const dotClass = item.team.region === 'Hohenlohe' ? 'hohenlohe'
                : item.team.region === 'Unterland' ? 'unterland'
                : 'unknown';
            const ort = item.team.adresse ? item.team.adresse.split(', ').pop() : '';
            return `
                <tr>
                    <td>${item.team.mannschaft}</td>
                    <td><span class="region-dot ${dotClass}"></span>${item.team.region}</td>
                    <td>${ort}</td>
                    <td>
                        <select class="filter-select edit-staffel-select" data-edit-idx="${idx}">
                            ${staffelOptions.replace(
                                `value="${item.staffelIdx}"`,
                                `value="${item.staffelIdx}" selected`
                            )}
                        </select>
                    </td>
                </tr>
            `;
        }).join('');

        // Store team refs for saving
        gruppenContainer._editTeams = allTeams;

        gruppenContainer.innerHTML = `
            <div class="edit-panel card">
                <div class="card-header">
                    <h3>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        ${g.altersklasse} ${g.topf} bearbeiten
                    </h3>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn btn-sm btn-primary" id="btnSaveEdit">Speichern</button>
                        <button class="btn btn-sm btn-secondary" id="btnCancelEdit">Abbrechen</button>
                    </div>
                </div>
                <div class="card-body" style="padding: 0;">
                    <table class="teams-table edit-table">
                        <thead>
                            <tr>
                                <th>Mannschaft</th>
                                <th>Region</th>
                                <th>Ort</th>
                                <th>Staffel</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        // Filter map to this gruppe
        mapGruppeFilter.value = String(editGruppeIdx);
        renderMap(resultData);

        // Bind save/cancel
        document.getElementById('btnSaveEdit').addEventListener('click', saveEdit);
        document.getElementById('btnCancelEdit').addEventListener('click', cancelEdit);
    }

    function saveEdit() {
        if (editGruppeIdx == null || !resultData) return;
        const g = resultData.gruppen[editGruppeIdx];
        const allTeams = gruppenContainer._editTeams;
        if (!allTeams) return;

        // Read new assignments from selects
        const selects = gruppenContainer.querySelectorAll('.edit-staffel-select');
        const newAssignments = [];
        selects.forEach((sel, idx) => {
            newAssignments.push({
                team: allTeams[idx].team,
                newStaffelIdx: parseInt(sel.value),
            });
        });

        // Clear all staffeln
        g.staffeln.forEach(s => {
            s.teams = [];
            s.n_teams = 0;
        });

        // Reassign
        newAssignments.forEach(({ team, newStaffelIdx }) => {
            g.staffeln[newStaffelIdx].teams.push(team);
            g.staffeln[newStaffelIdx].n_teams = g.staffeln[newStaffelIdx].teams.length;
        });

        // Update n_teams on gruppe
        g.n_teams = g.staffeln.reduce((s, st) => s + st.n_teams, 0);

        editGruppeIdx = null;
        renderGruppen(resultData.gruppen);
        renderMap(resultData);
        showToast('Änderungen gespeichert', 'success');
    }

    function cancelEdit() {
        editGruppeIdx = null;
        renderGruppen(resultData.gruppen);
    }

    // ─── Toast ───────────────────────────────────────────────
    function showToast(message, type = 'success') {
        toast.textContent = message;
        toast.className = `toast toast-${type} show`;
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }

    // ═══════════════════════════════════════════════════════════
    // ─── Spieltagsplanung Tab ────────────────────────────────
    // ═══════════════════════════════════════════════════════════

    const btnGenSpielplan = $('#btnGenSpielplan');
    const spStatusText = $('#spStatusText');
    const spStart = $('#sp-start');
    const spResults = $('#sp-results');
    const spStatsRow = $('#spStatsRow');
    const spFilterAk = $('#spFilterAk');
    const spielplanContainer = $('#spielplanContainer');
    const btnSpBack = $('#btnSpBack');
    const btnSpExpandAll = $('#btnSpExpandAll');
    const btnSpCollapseAll = $('#btnSpCollapseAll');

    let spielplanData = null;

    // Enable generate button when einteilung exists
    function updateSpielplanStatus() {
        if (resultData && resultData.gruppen && resultData.gruppen.length > 0) {
            const n = resultData.gruppen.reduce((s, g) => s + g.staffeln.length, 0);
            spStatusText.textContent = `Einteilung vorhanden: ${resultData.total_teams} Teams in ${n} Staffeln.`;
            btnGenSpielplan.disabled = false;
        } else {
            spStatusText.textContent = 'Bitte zuerst eine Staffeleinteilung berechnen.';
            btnGenSpielplan.disabled = true;
        }
    }

    // Hook into tab switching to refresh status
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.tab === 'spieltagsplanung') updateSpielplanStatus();
        });
    });

    // Generate Spielplan
    btnGenSpielplan.addEventListener('click', async () => {
        if (!resultData) return;

        loading.style.display = 'flex';
        const loadingText = loading.querySelector('.loading-text');
        if (loadingText) loadingText.textContent = 'Spielpläne werden generiert...';

        try {
            const resp = await fetch('/api/spielplan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ einteilung: resultData }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Server-Fehler');
            }

            spielplanData = await resp.json();
            renderSpielplanResults(spielplanData);
            spStart.style.display = 'none';
            spResults.style.display = 'block';
            showToast(`${spielplanData.total_staffeln} Spielpläne generiert!`, 'success');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            loading.style.display = 'none';
            if (loadingText) loadingText.textContent = 'Einteilung wird berechnet...';
        }
    });

    // Back button
    btnSpBack.addEventListener('click', () => {
        spResults.style.display = 'none';
        spStart.style.display = 'block';
    });

    // Render Spielplan results
    function renderSpielplanResults(data) {
        const plaene = data.spielplaene;

        // Stats
        const totalSpiele = plaene.reduce((s, p) =>
            s + p.spieltage.reduce((ss, st) => ss + st.spiele.length, 0), 0);
        const totalSpieltage = plaene.reduce((s, p) => s + p.spieltage.length, 0);
        const avgScore = plaene.filter(p => p.score).length > 0
            ? plaene.filter(p => p.score).reduce((s, p) => s + p.score.total, 0) / plaene.filter(p => p.score).length
            : 0;
        const konflikte = plaene.reduce((s, p) => s + (p.score ? p.score.platz_konflikte : 0), 0);

        spStatsRow.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${plaene.length}</div>
                <div class="stat-label">Spielpläne</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${totalSpieltage}</div>
                <div class="stat-label">Spieltage</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${totalSpiele}</div>
                <div class="stat-label">Spiele</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: ${konflikte > 0 ? 'var(--danger)' : 'var(--success)'}">
                    ${konflikte}
                </div>
                <div class="stat-label">Platzkonflikte</div>
            </div>
        `;

        // AK filter
        const altersklassen = [...new Set(plaene.map(p => p.altersklasse))].sort();
        spFilterAk.innerHTML = '<option value="">Alle Altersklassen</option>' +
            altersklassen.map(ak => `<option value="${ak}">${ak}</option>`).join('');

        renderSpielplaene(plaene);
    }

    function renderSpielplaene(plaene) {
        const akFilter = spFilterAk.value;
        const filtered = akFilter ? plaene.filter(p => p.altersklasse === akFilter) : plaene;

        if (filtered.length === 0) {
            spielplanContainer.innerHTML = `
                <div class="empty-state">
                    <p>Keine Spielpläne gefunden.</p>
                </div>
            `;
            return;
        }

        spielplanContainer.innerHTML = filtered.map((plan, idx) => {
            const drBadge = plan.doppelrunde
                ? '<span class="gruppe-badge badge-gold">Doppelrunde</span>' : '';
            const scoreBadge = plan.score
                ? `<span style="color: var(--text-muted); font-weight: 400; font-size: 0.85rem;">Score: ${plan.score.total}</span>` : '';

            // SZ table
            const szRows = plan.sz_zuordnungen.map(z =>
                `<tr><td>${z.mannschaft}</td><td style="text-align:center; font-weight:600;">${z.sz}</td></tr>`
            ).join('');

            // Spieltage
            const spieltageHtml = plan.spieltage.map(st => {
                const datumStr = st.datum
                    ? new Date(st.datum).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
                    : '–';
                const zeitStr = st.anstosszeit || '';

                const spieleRows = st.spiele.map(s =>
                    `<tr><td style="text-align:right; padding-right:0.5rem;">${s.heim}</td>
                     <td style="text-align:center; font-weight:600; color:var(--text-muted);">vs</td>
                     <td style="padding-left:0.5rem;">${s.gast}</td></tr>`
                ).join('');

                const spielfreiHtml = st.spielfrei
                    ? `<div class="spielfrei-hint">Spielfrei: ${st.spielfrei}</div>` : '';

                return `
                    <div class="spieltag-block">
                        <div class="spieltag-header">
                            <span class="spieltag-nr">Spieltag ${st.nummer}</span>
                            <span class="spieltag-datum">${datumStr}${zeitStr ? ' · ' + zeitStr : ''}</span>
                        </div>
                        <table class="spiele-table">
                            <tbody>${spieleRows}</tbody>
                        </table>
                        ${spielfreiHtml}
                    </div>
                `;
            }).join('');

            return `
                <div class="gruppe spielplan-gruppe">
                    <div class="gruppe-header" onclick="toggleGruppe(this)">
                        <div class="gruppe-title">
                            <span>${plan.altersklasse} ${plan.topf} – ${plan.staffel_name}</span>
                            ${drBadge}
                            <span style="color: var(--text-muted); font-weight: 400; font-size: 0.85rem;">
                                ${plan.n_teams} Teams · ${plan.spieltage.length} Spieltage
                            </span>
                        </div>
                        <div class="gruppe-meta">
                            ${scoreBadge}
                            <span class="gruppe-chevron">▼</span>
                        </div>
                    </div>
                    <div class="gruppe-body">
                        <div class="spielplan-content">
                            <div class="sz-section">
                                <h4>Schlüsselzahlen</h4>
                                <table class="teams-table sz-table">
                                    <thead><tr><th>Mannschaft</th><th style="text-align:center;">SZ</th></tr></thead>
                                    <tbody>${szRows}</tbody>
                                </table>
                            </div>
                            <div class="spieltage-section">
                                ${spieltageHtml}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    spFilterAk.addEventListener('change', () => {
        if (spielplanData) renderSpielplaene(spielplanData.spielplaene);
    });

    btnSpExpandAll.addEventListener('click', () => {
        document.querySelectorAll('#spielplanContainer .gruppe').forEach(g => g.classList.add('open'));
    });

    btnSpCollapseAll.addEventListener('click', () => {
        document.querySelectorAll('#spielplanContainer .gruppe').forEach(g => g.classList.remove('open'));
    });
})();
