/**
 * Staffel-Builder – Interaktiver Drag & Drop Staffel-Zuordner
 *
 * Jochen lädt seine Meldeliste hoch, bekommt alle Teams als Pool
 * und baut die Staffeln per Drag & Drop zusammen.
 */
(function () {
    'use strict';

    const $ = sel => document.querySelector(sel);
    const $$ = sel => document.querySelectorAll(sel);

    // ─── State ───────────────────────────────────────────────
    let selectedFile = null;
    let allTeams = [];          // flat array from API
    let pool = [];              // teams not yet assigned
    let staffeln = [];          // { id, name, typ, doppelrunde, teams: [] }
    let nextStaffelId = 1;
    let currentAk = '';         // selected AK filter
    let map = null;
    let mapLayers = [];
    let highlightedStaffelId = null;
    let draggedTeamId = null;
    let regiostaffeln = [];     // Regionenstaffeln from Hinrunde

    const STAFFEL_COLORS = [
        '#c41230', '#2563eb', '#059669', '#d97706', '#7c3aed',
        '#db2777', '#0891b2', '#65a30d', '#ea580c', '#4f46e5',
        '#0d9488', '#b91c1c', '#1d4ed8', '#15803d', '#a16207',
        '#6d28d9', '#be185d', '#0e7490', '#4d7c0f', '#c2410c',
    ];

    // ─── DOM refs ────────────────────────────────────────────
    const uploadSection = $('#builder-upload');
    const mainSection = $('#builder-main');
    const uploadZone = $('#uploadZone');
    const fileInput = $('#fileInput');
    const fileName = $('#fileName');
    const btnLoad = $('#btnLoad');
    const btnBackUpload = $('#btnBackUpload');
    const btnExport = $('#btnExport');
    const btnAddStaffel = $('#btnAddStaffel');
    const filterAk = $('#filterAk');
    const poolSearch = $('#poolSearch');
    const poolList = $('#poolList');
    const staffelnContainer = $('#staffelnContainer');
    const poolCounter = $('#poolCounter');
    const mapStaffelLabel = $('#mapStaffelLabel');
    const staffelTemplate = $('#staffelTemplate');
    const toast = $('#toast');

    // ─── Upload ──────────────────────────────────────────────
    uploadZone.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', e => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const f = e.dataTransfer.files[0];
        if (f && f.name.match(/\.xlsx?$/i)) { selectedFile = f; showFileName(f.name); }
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) { selectedFile = fileInput.files[0]; showFileName(selectedFile.name); }
    });

    function showFileName(name) {
        fileName.textContent = name;
        fileName.style.display = 'block';
        btnLoad.disabled = false;
    }

    // ─── Load teams ──────────────────────────────────────────
    btnLoad.addEventListener('click', async () => {
        if (!selectedFile) return;
        btnLoad.disabled = true;
        btnLoad.textContent = 'Lade Teams...';

        try {
            const fd = new FormData();
            fd.append('meldeliste', selectedFile);
            const resp = await fetch('/api/builder/teams', { method: 'POST', body: fd });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || 'Fehler beim Laden');
            }
            const data = await resp.json();
            allTeams = data.teams || [];

            // Populate AK filter
            const aks = [...new Set(allTeams.map(t => t.altersklasse))].sort();
            filterAk.innerHTML = '';
            aks.forEach((ak, i) => {
                const opt = document.createElement('option');
                opt.value = ak;
                opt.textContent = ak;
                if (i === 0) opt.selected = true;
                filterAk.appendChild(opt);
            });
            currentAk = aks[0] || '';

            // Reset builder state
            staffeln = [];
            nextStaffelId = 1;
            staffelnContainer.innerHTML = '';
            highlightedStaffelId = null;

            // Show builder
            uploadSection.style.display = 'none';
            mainSection.style.display = 'block';

            updatePool();
            initMap();
            renderMap();

            showToast(`${allTeams.length} Teams geladen`, 'success');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            btnLoad.disabled = false;
            btnLoad.textContent = 'Teams laden';
        }
    });

    btnBackUpload.addEventListener('click', () => {
        mainSection.style.display = 'none';
        uploadSection.style.display = 'block';
    });

    // ─── AK Filter ───────────────────────────────────────────
    filterAk.addEventListener('change', () => {
        currentAk = filterAk.value;
        // Reset staffeln when switching AK
        staffeln = [];
        nextStaffelId = 1;
        staffelnContainer.innerHTML = '';
        highlightedStaffelId = null;
        // Auto-populate Regionenstaffeln from Hinrunde
        populateRegiostaffeln();
        updatePool();
        renderMap();
    });

    function populateRegiostaffeln() {
        if (!regiostaffeln || regiostaffeln.length === 0) return;
        const akRegios = regiostaffeln.filter(r => r.altersklasse === currentAk);
        for (const regio of akRegios) {
            const s = addStaffel(regio.staffel_name, 'Regionenstaffel', false, true);
            // Match teams by name
            for (const teamName of regio.teams) {
                const team = allTeams.find(t =>
                    t.altersklasse === currentAk && t.mannschaft === teamName);
                if (team && !s.teams.find(x => x._id === team._id)) {
                    s.teams.push(team);
                }
            }
            renderStaffelTeams(s.id);
        }
    }

    // ─── Pool search ─────────────────────────────────────────
    poolSearch.addEventListener('input', () => renderPool());

    // ─── Pool update & render ────────────────────────────────
    function updatePool() {
        const assignedIds = new Set();
        for (const s of staffeln) {
            for (const t of s.teams) assignedIds.add(t._id);
        }
        pool = allTeams
            .filter(t => t.altersklasse === currentAk && !assignedIds.has(t._id));
        renderPool();
        updateCounters();
    }

    function renderPool() {
        const search = (poolSearch.value || '').toLowerCase();
        const filtered = search
            ? pool.filter(t => t.mannschaft.toLowerCase().includes(search) || (t.region || '').toLowerCase().includes(search))
            : pool;

        poolList.innerHTML = '';
        if (filtered.length === 0) {
            poolList.innerHTML = '<div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">' +
                (pool.length === 0 ? 'Alle Teams zugeordnet ✓' : 'Keine Treffer') + '</div>';
            return;
        }

        for (const t of filtered) {
            const el = document.createElement('div');
            el.className = 'builder-team-item';
            el.draggable = true;
            el.dataset.teamId = t._id;
            const hrInfo = t.hinrunde_staffel ? ` · ${esc(t.hinrunde_staffel)}` : '';
            el.innerHTML =
                `<span class="team-name">${esc(t.mannschaft)}</span>` +
                `<span class="team-meta">${esc(t.region || '?')}` +
                `${t.quotient_hinrunde != null ? ' · Q ' + t.quotient_hinrunde.toFixed(2) : ''}${hrInfo}</span>`;
            el.addEventListener('dragstart', onDragStart);
            el.addEventListener('dragend', onDragEnd);
            // Click = highlight on map
            el.addEventListener('click', () => highlightTeamOnMap(t));
            poolList.appendChild(el);
        }
    }

    function updateCounters() {
        const totalAk = allTeams.filter(t => t.altersklasse === currentAk).length;
        const assigned = totalAk - pool.length;
        poolCounter.textContent = `${assigned} / ${totalAk} Teams zugeordnet`;

        // Enable export when all teams assigned
        btnExport.disabled = pool.length > 0;

        // Update per-staffel counts
        for (const s of staffeln) {
            const countEl = document.querySelector(`[data-staffel-id="${s.id}"] .staffel-team-count`);
            if (countEl) countEl.textContent = `${s.teams.length} Teams`;
        }
    }

    // ─── Drag & Drop ─────────────────────────────────────────
    function onDragStart(e) {
        draggedTeamId = e.target.dataset.teamId;
        e.target.classList.add('dragging');
        e.dataTransfer.setData('text/plain', draggedTeamId);
        e.dataTransfer.effectAllowed = 'move';
        // Highlight all drop zones
        document.querySelectorAll('.builder-drop-zone').forEach(z => z.classList.add('drop-active'));
        // Also mark pool as drop target (for returning teams)
        poolList.classList.add('drop-active');
    }

    function onDragEnd(e) {
        draggedTeamId = null;
        e.target.classList.remove('dragging');
        document.querySelectorAll('.drop-active').forEach(z => z.classList.remove('drop-active'));
        document.querySelectorAll('.drop-hover').forEach(z => z.classList.remove('drop-hover'));
        poolList.classList.remove('drop-active');
    }

    // Pool as drop target (return teams)
    poolList.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        poolList.classList.add('drop-hover');
    });
    poolList.addEventListener('dragleave', () => poolList.classList.remove('drop-hover'));
    poolList.addEventListener('drop', e => {
        e.preventDefault();
        poolList.classList.remove('drop-hover');
        const teamId = e.dataTransfer.getData('text/plain');
        if (!teamId) return;
        // Remove from any staffel (but not locked ones)
        for (const s of staffeln) {
            if (s.locked) continue;
            const idx = s.teams.findIndex(t => t._id === teamId);
            if (idx >= 0) {
                s.teams.splice(idx, 1);
                renderStaffelTeams(s.id);
                break;
            }
        }
        updatePool();
        renderMap();
    });

    // ─── Staffel Management ──────────────────────────────────
    btnAddStaffel.addEventListener('click', () => addStaffel());

    function addStaffel(name, typ, doppelrunde, locked) {
        const id = nextStaffelId++;
        const s = {
            id,
            name: name || `Staffel ${id}`,
            typ: typ || 'Kreisstaffel',
            doppelrunde: doppelrunde || false,
            locked: locked || false,
            teams: [],
        };
        staffeln.push(s);

        const clone = staffelTemplate.content.cloneNode(true);
        const root = clone.querySelector('.builder-staffel');
        root.dataset.staffelId = id;

        const nameInput = clone.querySelector('.staffel-name-input');
        nameInput.value = s.name;
        nameInput.addEventListener('input', () => { s.name = nameInput.value; });

        const typSelect = clone.querySelector('.staffel-typ-select');
        typSelect.value = s.typ;
        typSelect.addEventListener('change', () => { s.typ = typSelect.value; });

        const drCheck = clone.querySelector('.staffel-dr-check');
        drCheck.checked = s.doppelrunde;
        drCheck.addEventListener('change', () => { s.doppelrunde = drCheck.checked; });

        const colorDot = clone.querySelector('.staffel-color-dot');
        colorDot.style.background = STAFFEL_COLORS[(id - 1) % STAFFEL_COLORS.length];

        clone.querySelector('.staffel-delete-btn').addEventListener('click', () => deleteStaffel(id));

        // Locked staffeln: disable editing
        if (s.locked) {
            root.classList.add('staffel-locked');
            nameInput.disabled = true;
            typSelect.disabled = true;
            drCheck.disabled = true;
            clone.querySelector('.staffel-delete-btn').style.display = 'none';
        }

        // Drop zone
        const dropZone = clone.querySelector('.builder-drop-zone');
        dropZone.addEventListener('dragover', e => {
            if (s.locked) return; // No drops into locked staffeln
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            dropZone.classList.add('drop-hover');
        });
        dropZone.addEventListener('dragleave', e => {
            if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove('drop-hover');
        });
        dropZone.addEventListener('drop', e => {
            if (s.locked) return; // No drops into locked staffeln
            e.preventDefault();
            dropZone.classList.remove('drop-hover');
            const teamId = e.dataTransfer.getData('text/plain');
            if (!teamId) return;

            // Remove from previous staffel (but not from locked ones)
            for (const other of staffeln) {
                if (other.locked) continue;
                const idx = other.teams.findIndex(t => t._id === teamId);
                if (idx >= 0) {
                    other.teams.splice(idx, 1);
                    renderStaffelTeams(other.id);
                    break;
                }
            }

            // Add to this staffel
            const team = allTeams.find(t => t._id === teamId);
            if (team && !s.teams.find(t => t._id === teamId)) {
                s.teams.push(team);
            }
            renderStaffelTeams(id);
            updatePool();
            renderMap();
        });

        // Click on staffel header = highlight on map
        clone.querySelector('.builder-staffel-header').addEventListener('click', e => {
            if (e.target.closest('input, select, button, label')) return;
            highlightedStaffelId = highlightedStaffelId === id ? null : id;
            updateStaffelHighlights();
            renderMap();
        });

        staffelnContainer.appendChild(clone);
        updateCounters();
        return s;
    }

    function deleteStaffel(id) {
        const idx = staffeln.findIndex(s => s.id === id);
        if (idx < 0 || staffeln[idx].locked) return;
        staffeln.splice(idx, 1);
        const el = document.querySelector(`[data-staffel-id="${id}"]`);
        if (el) el.remove();
        updatePool();
        renderMap();
    }

    function renderStaffelTeams(staffelId) {
        const s = staffeln.find(x => x.id === staffelId);
        if (!s) return;
        const zone = document.querySelector(`[data-staffel-id="${staffelId}"] .builder-drop-zone`);
        if (!zone) return;

        zone.innerHTML = '';
        if (s.teams.length === 0) {
            zone.innerHTML = '<div class="drop-placeholder">Teams hierher ziehen</div>';
            return;
        }

        for (const t of s.teams) {
            const el = document.createElement('div');
            el.className = 'builder-team-item in-staffel';
            el.draggable = !s.locked;
            el.dataset.teamId = t._id;
            el.innerHTML =
                `<span class="team-name">${esc(t.mannschaft)}</span>` +
                `<span class="team-meta">${esc(t.region || '?')}` +
                `${t.quotient_hinrunde != null ? ' · Q ' + t.quotient_hinrunde.toFixed(2) : ''}` +
                `${t.lat != null ? ' · 📍' : ''}</span>` +
                (s.locked ? '' : `<button class="team-remove-btn" title="Zurück in Pool">✕</button>`);
            if (!s.locked) {
                el.addEventListener('dragstart', onDragStart);
                el.addEventListener('dragend', onDragEnd);
            }
            el.addEventListener('click', e => {
                if (!s.locked && e.target.closest('.team-remove-btn')) {
                    // Remove from staffel
                    const idx = s.teams.findIndex(x => x._id === t._id);
                    if (idx >= 0) s.teams.splice(idx, 1);
                    renderStaffelTeams(staffelId);
                    updatePool();
                    renderMap();
                } else {
                    highlightTeamOnMap(t);
                }
            });
            zone.appendChild(el);
        }
    }

    function updateStaffelHighlights() {
        document.querySelectorAll('.builder-staffel').forEach(el => {
            el.classList.toggle('highlighted', Number(el.dataset.staffelId) === highlightedStaffelId);
        });
        const s = staffeln.find(x => x.id === highlightedStaffelId);
        mapStaffelLabel.textContent = s ? s.name : '';
    }

    // ─── Map ─────────────────────────────────────────────────
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

    function renderMap() {
        if (!map) return;
        mapLayers.forEach(l => map.removeLayer(l));
        mapLayers = [];
        const bounds = [];

        // Show only teams in current AK
        const akTeams = allTeams.filter(t => t.altersklasse === currentAk);

        // Pool teams = gray dots
        const assignedIds = new Set();
        for (const s of staffeln) {
            for (const t of s.teams) assignedIds.add(t._id);
        }

        for (const t of akTeams) {
            if (t.lat == null || t.lon == null) continue;
            if (assignedIds.has(t._id)) continue;

            const marker = L.circleMarker([t.lat, t.lon], {
                radius: 5,
                fillColor: '#9ca3af',
                color: '#fff',
                weight: 1,
                fillOpacity: 0.5,
            }).addTo(map);
            marker.bindPopup(`<strong>${esc(t.mannschaft)}</strong><br>${t.region || '?'}<br><small>Pool</small>`);
            mapLayers.push(marker);
            bounds.push([t.lat, t.lon]);
        }

        // Staffel teams = colored dots + hull
        for (const s of staffeln) {
            const color = STAFFEL_COLORS[(s.id - 1) % STAFFEL_COLORS.length];
            const isHighlighted = highlightedStaffelId === s.id || highlightedStaffelId == null;
            const opacity = isHighlighted ? 0.9 : 0.3;
            const coords = [];

            for (const t of s.teams) {
                if (t.lat == null || t.lon == null) continue;
                coords.push([t.lat, t.lon]);

                const marker = L.circleMarker([t.lat, t.lon], {
                    radius: isHighlighted ? 8 : 5,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    fillOpacity: opacity,
                }).addTo(map);
                marker.bindPopup(
                    `<strong>${esc(t.mannschaft)}</strong><br>` +
                    `${t.region || '?'}<br>` +
                    `<small>${s.name}</small>`
                );
                mapLayers.push(marker);
                bounds.push([t.lat, t.lon]);
            }

            if (coords.length >= 3 && isHighlighted) {
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
        }

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    function highlightTeamOnMap(team) {
        if (!map || team.lat == null || team.lon == null) return;
        map.setView([team.lat, team.lon], 12);
        // Flash effect
        const pulse = L.circleMarker([team.lat, team.lon], {
            radius: 15,
            fillColor: '#c41230',
            color: '#c41230',
            weight: 3,
            fillOpacity: 0.3,
        }).addTo(map);
        mapLayers.push(pulse);
        setTimeout(() => { map.removeLayer(pulse); }, 1500);
    }

    // ─── Convex Hull (Graham scan) ───────────────────────────
    function convexHull(points) {
        const pts = points.slice().sort((a, b) => a[1] - b[1] || a[0] - b[0]);
        if (pts.length <= 2) return pts;
        function cross(O, A, B) {
            return (A[1] - O[1]) * (B[0] - O[0]) - (A[0] - O[0]) * (B[1] - O[1]);
        }
        const lower = [];
        for (const p of pts) {
            while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
            lower.push(p);
        }
        const upper = [];
        for (const p of pts.slice().reverse()) {
            while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
            upper.push(p);
        }
        upper.pop();
        lower.pop();
        return lower.concat(upper);
    }

    // ─── Export ──────────────────────────────────────────────
    btnExport.addEventListener('click', async () => {
        try {
            btnExport.disabled = true;
            btnExport.textContent = 'Exportiere...';

            // Build gruppen structure matching the API format
            const gruppen = buildGruppenFromStaffeln();

            const resp = await fetch('/api/export/rueckrunde', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gruppen, saison: '2025/26' }),
            });
            if (!resp.ok) throw new Error('Export fehlgeschlagen');
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'Einteilung_Rueckrunde.xlsx';
            a.click();
            URL.revokeObjectURL(url);
            showToast('Excel exportiert', 'success');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            btnExport.disabled = pool.length > 0;
            btnExport.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Excel Export';
        }
    });

    function buildGruppenFromStaffeln() {
        // Group builder-staffeln by typ
        const typMap = {};
        for (const s of staffeln) {
            if (!typMap[s.typ]) typMap[s.typ] = [];
            typMap[s.typ].push(s);
        }

        const gruppen = [];
        for (const [typ, stList] of Object.entries(typMap)) {
            const gruppe = {
                altersklasse: currentAk,
                spielklasse: typ,
                topf: typ,
                n_teams: stList.reduce((sum, s) => sum + s.teams.length, 0),
                rueckrunde: true,
                staffeln: stList.map(s => ({
                    staffel_name: s.name,
                    n_teams: s.teams.length,
                    doppelrunde: s.doppelrunde,
                    teams: s.teams.map((t, i) => ({
                        mannschaft: t.mannschaft,
                        verein: t.verein || '',
                        adresse: t.adresse || '',
                        lat: t.lat || null,
                        lon: t.lon || null,
                        rang_hinrunde: t.rang_hinrunde || i + 1,
                        punkte_hinrunde: t.punkte_hinrunde || null,
                        quotient_hinrunde: t.quotient_hinrunde || null,
                        region: t.region || '?',
                    })),
                })),
            };
            gruppen.push(gruppe);
        }
        return gruppen;
    }

    // ─── Utilities ───────────────────────────────────────────
    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function showToast(msg, type) {
        toast.className = `toast show toast-${type}`;
        toast.textContent = msg;
        setTimeout(() => { toast.className = 'toast'; }, 3000);
    }

    // ─── Pre-load from Rückrunde tab ─────────────────────────
    function initFromRueckrunde() {
        const params = new URLSearchParams(window.location.search);
        const from = params.get('from');

        let raw = null;
        if (from === 'meldeliste') {
            raw = sessionStorage.getItem('builderTeams');
            sessionStorage.removeItem('builderTeams');
        } else if (from === 'rueckrunde') {
            raw = sessionStorage.getItem('builderData');
            sessionStorage.removeItem('builderData');
        }
        if (!raw) return;

        try {
            const data = JSON.parse(raw);

            if (from === 'meldeliste') {
                // Data comes from /api/builder/teams — already in the right format
                allTeams = data.teams || [];
                regiostaffeln = data.regiostaffeln || [];
            } else {
                // Data from rueckrunde tab — convert gruppen to flat team list
                const gruppen = data.gruppen || [];
                const neueTeams = data.neue_teams || [];
                let idCounter = 1;
                const teams = [];
                const seen = new Set();

                for (const g of gruppen) {
                    for (const s of g.staffeln || []) {
                        for (const t of s.teams || []) {
                            const key = (t.mannschaft || '') + '|' + (g.altersklasse || '');
                            if (seen.has(key)) continue;
                            seen.add(key);
                            teams.push({
                                _id: idCounter++,
                                mannschaft: t.mannschaft || '',
                                altersklasse: g.altersklasse || '',
                                verein: t.verein || '',
                                verein_nr: t.verein_nr || '',
                                region: t.region || '?',
                                lat: t.lat || null,
                                lon: t.lon || null,
                                rang_hinrunde: t.rang_hinrunde,
                                punkte_hinrunde: t.punkte_hinrunde,
                                quotient_hinrunde: t.quotient_hinrunde,
                                hinrunde_staffel: s.staffel_name || '',
                            });
                        }
                    }
                }

                for (const t of neueTeams) {
                    const key = (t.mannschaft || '') + '|' + (t.altersklasse || '');
                    if (seen.has(key)) continue;
                    seen.add(key);
                    teams.push({
                        _id: idCounter++,
                        mannschaft: t.mannschaft || '',
                        altersklasse: t.altersklasse || '',
                        verein: t.verein || '',
                        verein_nr: t.verein_nr || '',
                        region: t.region || '?',
                        lat: t.lat || null,
                        lon: t.lon || null,
                        rang_hinrunde: null,
                        punkte_hinrunde: null,
                        quotient_hinrunde: null,
                        hinrunde_staffel: '(neu)',
                    });
                }

                allTeams = teams;
            }

            // Populate AK filter
            const aks = [...new Set(allTeams.map(t => t.altersklasse))].sort();
            filterAk.innerHTML = '';
            aks.forEach((ak, i) => {
                const opt = document.createElement('option');
                opt.value = ak;
                opt.textContent = ak;
                if (i === 0) opt.selected = true;
                filterAk.appendChild(opt);
            });
            currentAk = aks[0] || '';

            // Reset builder state
            staffeln = [];
            nextStaffelId = 1;
            staffelnContainer.innerHTML = '';
            highlightedStaffelId = null;

            // Show builder
            uploadSection.style.display = 'none';
            mainSection.style.display = 'block';

            // Auto-populate Regionenstaffeln from Hinrunde
            populateRegiostaffeln();

            updatePool();
            initMap();
            renderMap();

            const nRegio = staffeln.filter(s => s.locked).length;
            const regioMsg = nRegio > 0 ? ` (${nRegio} Regionenstaffeln übernommen)` : '';
            showToast(`${allTeams.length} Teams geladen${regioMsg}`, 'success');
        } catch (err) {
            console.error('Fehler beim Laden:', err);
        }
    }

    initFromRueckrunde();

})();
