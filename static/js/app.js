        let allVideos = [];
        let currentStatusFilter = 'all';
        let sortDateAsc = false;
        let allTranscriptions = [];

        // Sidebar (hamburger) toggle
        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            if (!sidebar) return;
            sidebar.classList.toggle('collapsed');
        }

        // Tab switching (sidebar nav + content)
        // Per-tab URL routing. active_tab is injected by Flask (which route was hit);
        // TAB_PATHS maps each tab index to a real URL so tabs are shareable/bookmarkable.
        // INITIAL_TAB is injected inline by Flask in index.html before this file loads.
        window.INITIAL_TAB = window.INITIAL_TAB ?? 0;
        window.TAB_PATHS = ['/', '/transcriptions', '/graphrag', '/history', '/test'];

        const CRUMB = { 0: 'Ingest', 1: 'Library', 2: 'Ask', 3: 'History', 4: 'Test' };
        function switchTab(index, push = true, skipLoad = false) {
            document.querySelectorAll('.rail-item').forEach((tab) => {
                const i = parseInt(tab.getAttribute('data-tab'), 10);
                tab.classList.toggle('active', i === index);
            });
            document.querySelectorAll('.tab-content').forEach((content) => {
                content.classList.toggle('active', content.id === 'tab' + index);
            });
            const crumb = document.getElementById('crumb');
            if (crumb) crumb.textContent = CRUMB[index] || '';
            updateRefreshButtonVisibility(index);
            if (push && window.TAB_PATHS[index] && location.pathname !== window.TAB_PATHS[index]) {
                history.pushState({ tab: index }, '', window.TAB_PATHS[index]);
            }
            if (skipLoad) return; // caller drives the data load (e.g. Ask → open a specific source)
            if (index === 0) loadDownloadStatus();
            else if (index === 1) loadTranscriptions();
            else if (index === 3) loadHistory();
            else if (index === 4) initQuizTab();
        }

        // Browser back/forward → switch tab without re-pushing history.
        window.addEventListener('popstate', function (e) {
            let idx = (e.state && typeof e.state.tab === 'number')
                ? e.state.tab
                : window.TAB_PATHS.indexOf(location.pathname);
            if (idx < 0) idx = 0;  // '/downloads' and unknowns → Download Status
            switchTab(idx, false);
        });

        function updateRefreshButtonVisibility(activeIndex) {
            const btn = document.getElementById('refreshBtn');
            if (!btn) return;
            // Show only on Download Status (0) and Transcriptions (1)
            btn.style.display = (activeIndex === 0 || activeIndex === 1) ? 'inline-flex' : 'none';
        }

        // Auth: fill the rail user chip + dropdown menu (History/Admin/Logout live here now)
        let IS_LOGGED_IN = false;
        async function refreshAuthState() {
            try {
                const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
                const data = await res.json();
                const avatar = document.getElementById('userAvatar');
                const nameEl = document.getElementById('userName');
                const menu = document.getElementById('userMenu');
                if (!menu) return;
                if (data.success && data.user) {
                    IS_LOGGED_IN = true;
                    const u = data.user.username || 'user';
                    if (avatar) avatar.textContent = u.slice(0, 1).toUpperCase();
                    if (nameEl) nameEl.textContent = u;
                    let admin = '';
                    if (data.user.is_admin) {
                        const badge = data.user.admin_2fa_enabled ? '2FA On' : '2FA Off';
                        admin = '<div class="divider"></div><a href="/admin/2fa">🛡️ Admin 2FA <span style="margin-left:auto;color:#888;">' + badge + '</span></a>';
                    }
                    menu.innerHTML =
                        '<button type="button" onclick="closeUserMenu(); switchTab(3);">📋 History</button>' +
                        admin +
                        '<div class="divider"></div>' +
                        '<button type="button" class="danger" onclick="doLogout()">↩ Logout</button>';
                } else {
                    IS_LOGGED_IN = false;
                    if (avatar) avatar.textContent = '?';
                    if (nameEl) nameEl.textContent = 'Guest';
                    menu.innerHTML =
                        '<a href="/login">🔑 Login</a>' +
                        '<a href="/register">✍ Register</a>';
                }
            } catch (e) {
                console.error('Auth state:', e);
            }
        }
        function toggleUserMenu(e) {
            if (e) e.stopPropagation();
            const m = document.getElementById('userMenu');
            if (m) m.classList.toggle('open');
        }
        function closeUserMenu() {
            const m = document.getElementById('userMenu');
            if (m) m.classList.remove('open');
        }
        document.addEventListener('click', function (e) {
            const wrap = e.target.closest && e.target.closest('.rail-user');
            if (!wrap) closeUserMenu();
        });
        async function doLogout() {
            closeUserMenu();
            await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
            refreshAuthState();
            const tab3 = document.getElementById('tab3');
            if (tab3 && tab3.classList.contains('active')) switchTab(0);
            const hc = document.getElementById('historyContent');
            if (hc) hc.innerHTML = '<p style="color: #666;">Log in to see your transcription edit history and query history.</p>';
        }

        // History tab: load edit and query history (requires login)
        async function loadHistory() {
            const container = document.getElementById('historyContent');
            try {
                const [editsRes, queriesRes] = await Promise.all([
                    fetch('/api/history/edits?limit=50', { credentials: 'same-origin' }),
                    fetch('/api/history/queries?limit=50', { credentials: 'same-origin' })
                ]);
                if (editsRes.status === 401 || queriesRes.status === 401) {
                    container.innerHTML = '<p style="color: #666;">Log in to see your transcription edit history and query history.</p>';
                    return;
                }
                const editsData = await editsRes.json();
                const queriesData = await queriesRes.json();
                if (!editsData.success || !queriesData.success) {
                    container.innerHTML = '<p style="color: #666;">Could not load history.</p>';
                    return;
                }
                const edits = editsData.edits || [];
                const queries = queriesData.queries || [];
                let html = '<h3 style="margin-bottom: 12px;">📝 Edit history</h3>';
                html += '<div style="max-height: 280px; overflow-y: auto; margin-bottom: 24px;">';
                if (edits.length === 0) {
                    html += '<p style="color: #888;">No edits yet.</p>';
                } else {
                    html += '<table class="videos-table" style="width: 100%;"><thead><tr><th>Document</th><th>Chunk</th><th>Time</th><th>New text (preview)</th></tr></thead><tbody>';
                    edits.forEach(function(r) {
                        const preview = (r.new_text || '').slice(0, 80) + ((r.new_text || '').length > 80 ? '…' : '');
                        html += '<tr><td>' + escapeHtml(r.document_name) + '</td><td>' + r.chunk_id + '</td><td>' + escapeHtml(String(r.created_at || '')) + '</td><td>' + escapeHtml(preview) + '</td></tr>';
                    });
                    html += '</tbody></table>';
                }
                html += '</div><h3 style="margin-bottom: 12px;">🔍 Query history</h3><div style="max-height: 280px; overflow-y: auto;">';
                if (queries.length === 0) {
                    html += '<p style="color: #888;">No queries yet.</p>';
                } else {
                    html += '<table class="videos-table" style="width: 100%;"><thead><tr><th>Type</th><th>Time</th><th>Query (preview)</th><th>Results</th></tr></thead><tbody>';
                    queries.forEach(function(r) {
                        const preview = (r.query_text || '').slice(0, 60) + ((r.query_text || '').length > 60 ? '…' : '');
                        html += '<tr><td>' + escapeHtml(r.query_type || '') + '</td><td>' + escapeHtml(String(r.created_at || '')) + '</td><td>' + escapeHtml(preview) + '</td><td>' + (r.result_count != null ? r.result_count : '–') + '</td></tr>';
                    });
                    html += '</tbody></table>';
                }
                html += '</div>';
                container.innerHTML = html;
            } catch (e) {
                console.error('Load history:', e);
                container.innerHTML = '<p style="color: #666;">Log in to see your transcription edit history and query history.</p>';
            }
        }

        // Load download status
        async function loadDownloadStatus() {
            try {
                const response = await fetch('/api/download-status');
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    allVideos = data.videos;
                    updateStats(data);
                    renderVideos(allVideos);
                } else {
                    throw new Error(data.error || 'Failed to load download status');
                }
            } catch (error) {
                console.error('Error loading download status:', error);
                const tbody = document.getElementById('videosTableBody');
                if (tbody) {
                    tbody.innerHTML = 
                        '<tr><td colspan="5" style="text-align: center; color: red;">Error loading videos: ' + 
                        (error.message || 'Unknown error') + '</td></tr>';
                }
            }
        }

        // Update statistics — now feed the pipeline-rail counts (contextual, not a global bar)
        function updateStats(data) {
            const ingest = document.getElementById('countIngest');
            const library = document.getElementById('countLibrary');
            if (ingest) {
                const pending = data.pending || 0;
                ingest.textContent = pending ? pending : '';
                ingest.classList.toggle('warn', pending > 0);
                ingest.title = pending + ' pending / ' + (data.total || 0) + ' total';
            }
            if (library) {
                const n = data.with_transcriptions || 0;
                library.textContent = n ? n : '';
                library.title = n + ' transcriptions';
            }
        }

        // Render videos table
        function renderVideos(videos) {
            const tbody = document.getElementById('videosTableBody');

            if (videos.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px;">No videos found</td></tr>';
                return;
            }

            const sorted = [...videos].sort((a, b) => {
                const da = a.upload_date || '';
                const db = b.upload_date || '';
                if (da === db) return 0;
                return sortDateAsc ? (da < db ? -1 : 1) : (da > db ? -1 : 1);
            });

            tbody.innerHTML = sorted.map(video => {
                const displayStatus = video.transcription_exists ? 'completed' : video.status;
                const d = video.upload_date || '';
                const dateDisplay = d.length === 8
                    ? `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6)}`
                    : (d || '—');
                return `
                <tr>
                    <td>${escapeHtml(video.title)}</td>
                    <td style="white-space:nowrap; color:#a0a0a0;">${dateDisplay}</td>
                    <td><span class="status-badge status-${displayStatus}">${displayStatus}</span></td>
                    <td>
                        <span class="file-indicator ${video.wav_exists ? 'file-exists' : 'file-missing'}"></span>
                        ${video.wav_exists ? 'Yes' : 'No'}
                    </td>
                    <td>
                        <span class="file-indicator ${video.transcription_exists ? 'file-exists' : 'file-missing'}"></span>
                        ${video.transcription_exists ? 'Yes' : 'No'}
                    </td>
                    <td><a href="${video.url}" target="_blank" style="color: var(--accent-bright);">View</a></td>
                </tr>
            `;
            }).join('');
        }

        function toggleSortByDate() {
            sortDateAsc = !sortDateAsc;
            const btn = document.getElementById('sortDateBtn');
            btn.textContent = `上傳日期 ${sortDateAsc ? '↑' : '↓'}`;
            filterVideos();
        }

        // Filter by status
        function filterByStatus(status) {
            currentStatusFilter = status;
            
            // Update filter buttons
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Filter videos
            let filtered = allVideos;
            if (status !== 'all') {
                // For completed filter, include videos with transcriptions (transcription = completed)
                if (status === 'completed') {
                    filtered = allVideos.filter(v => v.transcription_exists || v.status === 'completed');
                } else {
                    // For other statuses, exclude videos with transcriptions (they're considered completed)
                    filtered = allVideos.filter(v => v.status === status && !v.transcription_exists);
                }
            }
            
            renderVideos(filtered);
        }

        // Search videos
        function filterVideos() {
            const searchTerm = document.getElementById('searchBox').value.toLowerCase();
            let filtered = allVideos;
            
            if (currentStatusFilter !== 'all') {
                // For completed filter, include videos with transcriptions (transcription = completed)
                if (currentStatusFilter === 'completed') {
                    filtered = filtered.filter(v => v.transcription_exists || v.status === 'completed');
                } else {
                    // For other statuses, exclude videos with transcriptions (they're considered completed)
                    filtered = filtered.filter(v => v.status === currentStatusFilter && !v.transcription_exists);
                }
            }
            
            if (searchTerm) {
                filtered = filtered.filter(v => 
                    v.title.toLowerCase().includes(searchTerm) ||
                    v.url.toLowerCase().includes(searchTerm)
                );
            }
            
            renderVideos(filtered);
        }

        // Load transcriptions
        async function loadTranscriptions() {
            try {
                const response = await fetch('/api/transcriptions');
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    allTranscriptions = data.transcriptions;
                    renderTranscriptions(allTranscriptions);
                } else {
                    throw new Error(data.error || 'Failed to load transcriptions');
                }
            } catch (error) {
                console.error('Error loading transcriptions:', error);
                const container = document.getElementById('transcriptionsList');
                if (container) {
                    container.innerHTML = 
                        '<div style="text-align: center; padding: 40px; color: red;">Error loading transcriptions: ' + 
                        (error.message || 'Unknown error') + '</div>';
                }
            }
        }

        // Render transcriptions
        function renderTranscriptions(transcriptions) {
            const container = document.getElementById('transcriptionsList');
            
            if (transcriptions.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px;">No transcriptions found</div>';
                return;
            }

            container.innerHTML = transcriptions.map((trans, index) => `
                <div class="transcription-item" id="trans-${index}">
                    <div class="transcription-header" onclick="toggleTranscription(${index})">
                        <div>
                            <div class="transcription-title">${escapeHtml(trans.title)}</div>
                            <div class="transcription-meta">
                                <span>📄 ${trans.filename}</span>
                                <span>📝 ${trans.char_count.toLocaleString()} chars</span>
                            </div>
                        </div>
                        <div class="transcription-toggle">▼</div>
                    </div>
                    <div class="transcription-content" id="trans-content-${index}">
                        <div style="text-align: center; padding: 20px;">
                            <div class="loading"></div>Loading content...
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // YouTube: extract 11-char video id from watch / youtu.be / shorts / embed links,
        // a bare id, or a watch URL where v= is not the first query param.
        function getYoutubeId(url) {
            if (!url || typeof url !== 'string') return null;
            const s = url.trim();
            if (/^[a-zA-Z0-9_-]{11}$/.test(s)) return s; // already a bare id
            try {
                const u = new URL(s.startsWith('http') ? s : 'https://' + s);
                const host = u.hostname.replace(/^www\.|^m\./, '');
                if (host === 'youtu.be') {
                    const id = u.pathname.slice(1, 12);
                    return /^[a-zA-Z0-9_-]{11}$/.test(id) ? id : null;
                }
                if (host === 'youtube.com') {
                    const v = u.searchParams.get('v');
                    if (v && /^[a-zA-Z0-9_-]{11}$/.test(v)) return v;
                    const m = u.pathname.match(/\/(?:embed|shorts|v)\/([a-zA-Z0-9_-]{11})/);
                    if (m) return m[1];
                }
            } catch (e) { /* fall through */ }
            const m = s.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/);
            return m ? m[1] : null;
        }

        // ---- YouTube IFrame API player (controllable: load + seek) ----
        let ytPlayer = null;      // YT.Player instance (created lazily)
        let ytApiReady = false;   // set by onYouTubeIframeAPIReady
        let ytPending = null;     // { videoId, start } queued before API is ready

        window.onYouTubeIframeAPIReady = function () {
            ytApiReady = true;
            if (ytPending) { _ytApply(ytPending); ytPending = null; }
        };
        let ytPlayerReady = false;   // true once the created player fires onReady
        function _ytApply({ videoId, start }) {
            if (!videoId) return;
            const startSeconds = (start != null) ? Math.max(0, Math.floor(start)) : undefined;
            if (ytPlayer && ytPlayer.loadVideoById && ytPlayerReady) {
                // reuse existing player — load at the timestamp natively
                ytPlayer.loadVideoById(startSeconds != null ? { videoId, startSeconds } : { videoId });
            } else if (ytPlayer && !ytPlayerReady) {
                // player still initialising — remember what to load once ready
                ytPending = { videoId, start };
            } else {
                ytPlayer = new YT.Player('transcriptionYoutubePlayer', {
                    width: '100%', height: '100%', videoId,
                    playerVars: { rel: 0, enablejsapi: 1, playsinline: 1, start: startSeconds, origin: location.origin },
                    events: {
                        onReady: function () {
                            ytPlayerReady = true;
                            if (ytPending) { const p = ytPending; ytPending = null; _ytApply(p); }
                        }
                    }
                });
            }
        }
        function loadVideoInPlayer(videoId, start) {
            if (ytApiReady && window.YT && window.YT.Player) _ytApply({ videoId, start });
            else ytPending = { videoId, start };
        }
        function seekPlayer(seconds) {
            const s = parseFloat(seconds);
            if (isNaN(s)) return;
            if (ytPlayer && ytPlayerReady && ytPlayer.seekTo) {
                ytPlayer.seekTo(s, true);
                if (ytPlayer.playVideo) ytPlayer.playVideo();
            } else if (ytPending) {
                ytPending.start = s; // player still loading — start there once ready
            } else {
                toast.info('Select this transcription first, then use ▶');
            }
        }
        function setRightVideoAspect(width, height) {
            const right = document.querySelector('.transcriptions-right');
            if (!right) return;
            if (width && height) {
                right.style.setProperty('--video-aspect-ratio', `${width} / ${height}`);
            } else {
                right.style.setProperty('--video-aspect-ratio', '16 / 9');
            }
        }

        async function fetchVideoAspect(url) {
            if (!url) return null;
            try {
                const res = await fetch(`/api/video-aspect?url=${encodeURIComponent(url)}`);
                const data = await res.json();
                if (res.ok && data.success && data.width && data.height) {
                    return { width: data.width, height: data.height };
                }
            } catch (e) {
                console.warn('video aspect fetch failed', e);
            }
            return null;
        }

        async function setTranscriptionYoutubeVideo(url, startSeconds) {
            const placeholder = document.getElementById('transcriptionYoutubePlaceholder');
            const wrap = document.getElementById('transcriptionYoutubeWrap');
            const right = document.querySelector('.transcriptions-right');
            const videoId = getYoutubeId(url);
            if (videoId) {
                setRightVideoAspect(null, null); // start with default before metadata resolves
                // Reveal + size the container BEFORE creating the player — YT.Player built
                // inside a display:none / 0×0 box often never renders the video.
                if (wrap) wrap.style.display = 'block';
                if (placeholder) placeholder.style.display = 'none';
                if (right) right.classList.add('has-video');
                loadVideoInPlayer(videoId, startSeconds != null ? startSeconds : null);
                const dims = await fetchVideoAspect(url);
                if (dims) {
                    setRightVideoAspect(dims.width, dims.height);
                }
            } else {
                if (ytPlayer && ytPlayer.stopVideo) ytPlayer.stopVideo();
                if (wrap) wrap.style.display = 'none';
                if (placeholder) placeholder.style.display = 'flex';
                if (right) right.classList.remove('has-video');
                setRightVideoAspect(null, null);
            }
        }

        // Toggle transcription
        async function toggleTranscription(index, startSeconds) {
            const item = document.getElementById(`trans-${index}`);
            const content = document.getElementById(`trans-content-${index}`);
            const transcription = allTranscriptions[index];

            if (item.classList.contains('expanded') && startSeconds == null) {
                item.classList.remove('expanded');
            } else {
                item.classList.add('expanded');
                await setTranscriptionYoutubeVideo(transcription.url || '', startSeconds);
                
                // Load content if not loaded
                if (content.textContent.includes('Loading content')) {
                    try {
                        // Load chunks with metadata
                        const chunksResponse = await fetch(`/api/transcription/chunks/${encodeURIComponent(transcription.filename)}`);
                        
                        if (!chunksResponse.ok) {
                            throw new Error(`HTTP error! status: ${chunksResponse.status}`);
                        }
                        
                        const chunksData = await chunksResponse.json();
                        
                        if (chunksData.success && chunksData.chunks) {
                            // Render chunks with edit capability; ▶ only if this transcription has a playable video
                            const hasVideo = !!getYoutubeId(transcription.url || '');
                            renderChunksWithEdit(content, chunksData.chunks, transcription.filename, hasVideo);
                        } else {
                            // Fallback to old method
                            const response = await fetch(`/api/transcription/${encodeURIComponent(transcription.filename)}`);
                            
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            
                            const data = await response.json();
                            
                            if (data.success) {
                                const formatted = formatTranscription(data.content);
                                content.innerHTML = formatted;
                            } else {
                                content.innerHTML = `<div class="error-message">Error loading transcription: ${data.error || 'Unknown error'}</div>`;
                            }
                        }
                    } catch (error) {
                        console.error('Error loading transcription:', error);
                        content.innerHTML = `<div class="error-message">Error loading transcription: ${error.message || 'Unknown error'}</div>`;
                    }
                }
            }
        }

        // Render chunks with edit capability
        function renderChunksWithEdit(container, chunks, filename, hasVideo) {
            if (!chunks || chunks.length === 0) {
                container.innerHTML = '<div class="error-message">No chunks found in transcription file</div>';
                return;
            }
            
            container.innerHTML = chunks.map((chunk, index) => {
                const chunkId = chunk.chunk_id !== undefined ? chunk.chunk_id : index;
                const text = chunk.text || '';
                let timecode = '';
                let seekBtn = '';
                const hasStart = chunk.start_time !== null && chunk.start_time !== undefined;
                if (hasStart && chunk.end_time !== null && chunk.end_time !== undefined) {
                    try {
                        timecode = `[${parseFloat(chunk.start_time).toFixed(2)}s - ${parseFloat(chunk.end_time).toFixed(2)}s]`;
                    } catch (e) {
                        timecode = '';
                    }
                }
                if (hasStart && hasVideo) {
                    const startSec = parseFloat(chunk.start_time);
                    // ▶ seeks the YouTube player on the right to this chunk's start.
                    // Only shown when the transcription actually has a playable video.
                    seekBtn = `<button class="chunk-seek" onclick="seekPlayer(${startSec})" title="Play video from here">▶</button>`;
                }
                
                // Escape filename for use in JavaScript string
                const escapedFilename = filename.replace(/'/g, "\\'").replace(/"/g, '\\"');
                
                return `
                    <div class="transcription-chunk" id="chunk-${chunkId}">
                        <div class="transcription-chunk-header">
                            <span>${seekBtn}Chunk ${chunkId + 1} ${timecode}</span>
                            <div class="chunk-actions">
                                <button class="edit-btn" onclick="editChunk(${chunkId}, '${escapedFilename}')">✏️ Edit</button>
                                <button class="delete-btn" onclick="deleteChunk(${chunkId}, '${escapedFilename}')">🗑️ Delete</button>
                            </div>
                        </div>
                        <div class="chunk-content" id="chunk-content-${chunkId}">${escapeHtml(text)}</div>
                        <div class="chunk-editor" id="chunk-editor-${chunkId}" style="display: none;">
                            <textarea class="chunk-edit-textarea" id="chunk-textarea-${chunkId}">${escapeHtml(text)}</textarea>
                            <div class="chunk-edit-actions">
                                <button class="btn btn-primary" onclick="saveChunk(${chunkId}, '${escapedFilename}')">💾 Save</button>
                                <button class="btn btn-secondary" onclick="cancelEdit(${chunkId})">❌ Cancel</button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Edit chunk
        function editChunk(chunkId, filename) {
            const contentDiv = document.getElementById(`chunk-content-${chunkId}`);
            const editorDiv = document.getElementById(`chunk-editor-${chunkId}`);
            const textarea = document.getElementById(`chunk-textarea-${chunkId}`);
            
            contentDiv.style.display = 'none';
            editorDiv.style.display = 'block';
            textarea.focus();
        }

        // Cancel edit
        function cancelEdit(chunkId) {
            const contentDiv = document.getElementById(`chunk-content-${chunkId}`);
            const editorDiv = document.getElementById(`chunk-editor-${chunkId}`);
            
            contentDiv.style.display = 'block';
            editorDiv.style.display = 'none';
        }

        // Delete chunk
        async function deleteChunk(chunkId, filename) {
            const ok = await confirmDialog({
                title: `Delete Chunk ${chunkId + 1}?`,
                message: 'This action cannot be undone.',
                confirmText: 'Delete',
                danger: true,
            });
            if (!ok) return;

            const chunkElement = document.getElementById(`chunk-${chunkId}`);
            if (!chunkElement) {
                toast.error('Chunk element not found');
                return;
            }
            
            // Show loading state
            chunkElement.style.opacity = '0.5';
            chunkElement.style.pointerEvents = 'none';
            const originalHTML = chunkElement.innerHTML;
            chunkElement.innerHTML = '<div style="text-align: center; padding: 20px;"><div class="loading"></div>Deleting chunk...</div>';
            
            try {
                const response = await fetch('/api/transcription/delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        filename: filename,
                        chunk_id: chunkId
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    // Remove the chunk element from the DOM
                    chunkElement.remove();
                    
                    // Show success message
                    const container = chunkElement.parentElement;
                    if (container) {
                        const successMsg = document.createElement('div');
                        successMsg.className = 'success-message';
                        successMsg.textContent = `Chunk ${chunkId + 1} deleted successfully`;
                        successMsg.style.marginBottom = '10px';
                        container.insertBefore(successMsg, container.firstChild);
                        
                        // Remove success message after 3 seconds
                        setTimeout(() => {
                            successMsg.remove();
                        }, 3000);
                    }
                } else {
                    throw new Error(data.error || 'Failed to delete chunk');
                }
            } catch (error) {
                console.error('Error deleting chunk:', error);
                // Restore original state
                chunkElement.style.opacity = '1';
                chunkElement.style.pointerEvents = 'auto';
                chunkElement.innerHTML = originalHTML;
                toast.error(`Error deleting chunk: ${error.message || 'Unknown error'}`);
            }
        }

        // Save chunk
        async function saveChunk(chunkId, filename) {
            const textarea = document.getElementById(`chunk-textarea-${chunkId}`);
            const newText = textarea.value.trim();
            const contentDiv = document.getElementById(`chunk-content-${chunkId}`);
            const editorDiv = document.getElementById(`chunk-editor-${chunkId}`);
            
            if (!newText) {
                toast.error('Text cannot be empty');
                return;
            }
            
            // Show loading state
            const saveBtn = editorDiv.querySelector('.btn-primary');
            const originalText = saveBtn.textContent;
            saveBtn.textContent = '⏳ Saving...';
            saveBtn.disabled = true;
            
            try {
                const response = await fetch('/api/transcription/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        filename: filename,
                        chunk_id: chunkId,
                        new_text: newText
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Update displayed content
                    contentDiv.textContent = newText;
                    contentDiv.style.display = 'block';
                    editorDiv.style.display = 'none';
                    toast.success('Chunk updated in file and Neo4j');
                } else {
                    toast.error(`Error: ${data.error || 'Failed to update chunk'}`);
                }
            } catch (error) {
                toast.error(`Error: ${error.message}`);
            } finally {
                saveBtn.textContent = originalText;
                saveBtn.disabled = false;
            }
        }

        // Format transcription content
        function formatTranscription(content) {
            // Split by chunk markers
            const chunks = content.split(/=== Chunk \d+ ===/);
            
            return chunks.map((chunk, index) => {
                const text = chunk.trim();
                if (!text) return '';
                
                return `
                    <div class="transcription-chunk">
                        <div class="transcription-chunk-header">Chunk ${index}</div>
                        <div>${escapeHtml(text)}</div>
                    </div>
                `;
            }).join('');
        }

        // Execute natural language query using LLM agent
        // ---- Ask: chat surface ----
        let ASK_SOURCES = [];   // sources of the most recent answer (for citation chips)
        let askGraphCy = null;  // cytoscape instance

        function askScrollBottom() {
            const t = document.getElementById('askThread');
            if (t) t.scrollTop = t.scrollHeight;
        }
        function askAppend(cls, innerHtml) {
            const thread = document.getElementById('askThread');
            const empty = document.getElementById('askEmpty');
            if (empty) empty.style.display = 'none';
            const el = document.createElement('div');
            el.className = 'msg ' + cls;
            el.innerHTML = innerHtml;
            thread.appendChild(el);
            askScrollBottom();
            return el;
        }
        function askAutogrow(el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 140) + 'px';
        }
        function askComposerKey(e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); executeNLQuery(); }
        }
        function askSuggest(btn) {
            const input = document.getElementById('nlQuery');
            input.value = btn.textContent;
            executeNLQuery();
        }
        function citeChips(sources) {
            if (!sources.length) return '';
            const chips = sources.map((s, i) => {
                const score = (typeof s.score === 'number') ? s.score.toFixed(2) : '';
                const via = s.via === 'concept' ? '🔑' : '🔍';
                const doc = escapeHtml((s.doc || '?').slice(0, 22));
                return `<span class="cite-chip" onclick="openSource(${i})" title="${escapeHtml(s.text || '')}">
                    <span class="cc-via">${via}</span>${doc}<span class="cc-score">${score}</span></span>`;
            }).join('');
            return `<div class="cites">${chips}</div>`;
        }
        // Ask citation chip → open that transcription in Library and seek the player to the chunk.
        async function openSource(i) {
            const s = ASK_SOURCES[i];
            if (!s) return;
            switchTab(1, true, true);            // show Library, but don't let it auto-reload the list
            await openTranscriptionByDoc(s.doc, s.start);
        }
        // Fuzzy-match an Ask source's doc name to a transcription in the Library list.
        function findTranscriptionIndex(doc) {
            if (!doc || !allTranscriptions) return -1;
            const strip = (x) => (x || '').toLowerCase().replace(/\.(txt|json|srt|vtt)$/i, '').trim();
            const d = strip(doc);
            let idx = allTranscriptions.findIndex(t => (t.filename || '').toLowerCase() === (doc || '').toLowerCase());
            if (idx < 0) idx = allTranscriptions.findIndex(t => strip(t.filename) === d);
            if (idx < 0) idx = allTranscriptions.findIndex(t => strip(t.title) === d);
            if (idx < 0) idx = allTranscriptions.findIndex(t => strip(t.filename).includes(d) || d.includes(strip(t.filename)));
            return idx;
        }
        async function openTranscriptionByDoc(doc, start) {
            // ensure the list exists (we skipped switchTab's auto-load)
            if (!allTranscriptions || !allTranscriptions.length) await loadTranscriptions();
            const idx = findTranscriptionIndex(doc);
            if (idx < 0) {
                toast.info('Source “' + (doc || '?') + '” not found in Library');
                return;
            }
            const item = document.getElementById('trans-' + idx);
            if (item && item.classList.contains('expanded')) {
                // already open — just (re)load the video at the timestamp
                await setTranscriptionYoutubeVideo(allTranscriptions[idx].url || '', start);
            } else {
                await toggleTranscription(idx, start != null ? start : undefined);
            }
            if (item) item.scrollIntoView({ behavior: 'smooth', block: 'start' });
            if (start != null) seekPlayer(start);
        }
        function renderAskGraph(query, sources) {
            const pane = document.getElementById('askGraphPane');
            const canvas = document.getElementById('askGraphCanvas');
            if (!pane || !canvas || typeof cytoscape === 'undefined' || !sources.length) {
                if (pane) pane.classList.remove('show');
                return;
            }
            const nodes = [{ data: { id: 'q', label: query.slice(0, 24), kind: 'q' } }];
            const edges = [];
            sources.forEach((s, i) => {
                const id = 'n' + i;
                nodes.push({ data: { id, label: (s.doc || '?').slice(0, 16), kind: s.via === 'concept' ? 'concept' : 'chunk' } });
                edges.push({ data: { source: 'q', target: id } });
            });
            if (askGraphCy) { askGraphCy.destroy(); askGraphCy = null; }
            askGraphCy = cytoscape({
                container: canvas,
                elements: { nodes, edges },
                style: [
                    { selector: 'node', style: {
                        'label': 'data(label)', 'color': '#ddd', 'font-size': '9px',
                        'text-valign': 'center', 'text-halign': 'center',
                        'text-max-width': '70px', 'text-wrap': 'ellipsis',
                        'width': 26, 'height': 26, 'background-color': '#555' } },
                    { selector: 'node[kind="q"]', style: { 'background-color': '#FEAE02', 'color': '#1a1200', 'width': 34, 'height': 34, 'font-weight': 'bold' } },
                    { selector: 'node[kind="concept"]', style: { 'background-color': '#D39B05' } },
                    { selector: 'node[kind="chunk"]', style: { 'background-color': '#4a4a4a' } },
                    { selector: 'edge', style: { 'width': 1.5, 'line-color': '#3a3a3a', 'curve-style': 'bezier' } },
                ],
                layout: { name: 'concentric', concentric: n => (n.data('kind') === 'q' ? 2 : 1), levelWidth: () => 1, minNodeSpacing: 24 },
            });
            askGraphCy.on('tap', 'node[kind!="q"]', (evt) => {
                const idx = parseInt(evt.target.id().slice(1), 10);
                if (!isNaN(idx)) openSource(idx);
            });
            pane.classList.add('show');
        }
        async function executeNLQuery() {
            const queryInput = document.getElementById('nlQuery');
            if (!queryInput) return;
            const query = queryInput.value.trim();
            if (!query) { toast.info('Type a question first'); return; }

            const sendBtn = document.getElementById('askSendBtn');
            askAppend('msg-you', `<div class="bubble">${escapeHtml(query)}</div>`);
            queryInput.value = '';
            askAutogrow(queryInput);
            if (sendBtn) sendBtn.disabled = true;

            const aiEl = askAppend('msg-ai', `<div class="bubble"><span class="thinking"><span></span><span></span><span></span></span></div>`);
            const bubble = aiEl.querySelector('.bubble');

            try {
                const response = await fetch('/api/graphrag/nl-query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query })
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();

                if (data.success) {
                    const answer = data.answer || 'No answer generated.';
                    const resultsCount = data.results_count || 0;
                    const llmLabel = (data.llm_backend === 'ollama') ? 'Ollama (local)' : 'OpenAI';
                    ASK_SOURCES = data.sources || [];
                    bubble.innerHTML =
                        `<div class="answer">${escapeHtml(answer)}</div>` +
                        citeChips(ASK_SOURCES) +
                        `<div class="msg-meta">${escapeHtml(llmLabel)}${resultsCount ? ' · ' + resultsCount + ' graph result' + (resultsCount !== 1 ? 's' : '') : ''}</div>`;
                    renderAskGraph(query, ASK_SOURCES);
                } else {
                    bubble.innerHTML = `<div class="answer" style="color:#ff8a8a;">${escapeHtml(data.error || 'Query failed')}</div>`;
                }
            } catch (error) {
                console.error('Error executing NL query:', error);
                bubble.innerHTML = `<div class="answer" style="color:#ff8a8a;">Error: ${escapeHtml(error.message || 'Unknown error')}</div>`;
            } finally {
                if (sendBtn) sendBtn.disabled = false;
                askScrollBottom();
            }
        }

        // ---- Command palette (Ctrl/⌘ K) ----
        const OMNI_STAGES = [
            { ico: '🕸️', label: 'Ask the graph', sub: 'Ask', tab: 2 },
            { ico: '📥', label: 'Ingest / Download status', sub: 'Ingest', tab: 0 },
            { ico: '📚', label: 'Library / Transcriptions', sub: 'Library', tab: 1 },
            { ico: '📝', label: 'Knowledge Test', sub: 'Test', tab: 4 },
        ];
        function renderOmniActions(filter) {
            const box = document.getElementById('omniActions');
            const q = (filter || '').trim().toLowerCase();
            let rows = '';
            if (q) {
                rows += `<div class="omni-action sel" data-ask="1"><span class="oa-ico">🕸️</span>Ask: “${escapeHtml(filter)}”<span class="oa-sub">Enter</span></div>`;
            }
            OMNI_STAGES
                .filter(s => !q || s.label.toLowerCase().includes(q) || s.sub.toLowerCase().includes(q))
                .forEach((s, i) => {
                    rows += `<div class="omni-action${(!q && i === 0) ? ' sel' : ''}" data-tab="${s.tab}"><span class="oa-ico">${s.ico}</span>${s.label}<span class="oa-sub">${s.sub}</span></div>`;
                });
            box.innerHTML = rows;
            box.querySelectorAll('.omni-action').forEach(el => {
                el.addEventListener('click', () => omniRun(el));
            });
        }
        function openOmni() {
            const ov = document.getElementById('omniOverlay');
            const inp = document.getElementById('omniInput');
            ov.classList.add('open');
            inp.value = '';
            renderOmniActions('');
            setTimeout(() => inp.focus(), 20);
        }
        function closeOmni() {
            const ov = document.getElementById('omniOverlay');
            if (ov) ov.classList.remove('open');
        }
        function omniRun(el) {
            if (el.dataset.ask) {
                const q = document.getElementById('omniInput').value.trim();
                closeOmni();
                switchTab(2);
                const nl = document.getElementById('nlQuery');
                if (nl) { nl.value = q; executeNLQuery(); }
            } else if (el.dataset.tab != null) {
                closeOmni();
                switchTab(parseInt(el.dataset.tab, 10));
            }
        }
        function omniKey(e) {
            const box = document.getElementById('omniActions');
            if (e.key === 'Escape') { closeOmni(); return; }
            if (e.key === 'Enter') {
                const sel = box.querySelector('.omni-action.sel') || box.querySelector('.omni-action');
                if (sel) omniRun(sel);
                return;
            }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const items = [...box.querySelectorAll('.omni-action')];
                let idx = items.findIndex(i => i.classList.contains('sel'));
                items.forEach(i => i.classList.remove('sel'));
                idx = e.key === 'ArrowDown' ? (idx + 1) % items.length : (idx - 1 + items.length) % items.length;
                if (items[idx]) items[idx].classList.add('sel');
                return;
            }
            setTimeout(() => renderOmniActions(e.target.value), 0);
        }
        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                e.preventDefault();
                const ov = document.getElementById('omniOverlay');
                if (ov && ov.classList.contains('open')) closeOmni(); else openOmni();
            }
        });

        // Execute GraphRAG query
        async function executeQuery() {
            const queryInput = document.getElementById('cypherQuery');
            const resultsDiv = document.getElementById('queryResults');
            
            if (!queryInput || !resultsDiv) {
                console.error('Query elements not found');
                return;
            }
            
            const query = queryInput.value.trim();
            
            if (!query) {
                resultsDiv.innerHTML = '<div class="error-message">Please enter a query</div>';
                resultsDiv.classList.add('empty');
                return;
            }
            
            resultsDiv.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="loading"></div>Executing query...</div>';
            resultsDiv.classList.remove('empty');
            
            try {
                const response = await fetch('/api/graphrag/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ query: query })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    if (data.results && data.results.length > 0) {
                        // For Cypher queries, show a summary instead of graph
                        const resultsCount = data.results.length;
                        resultsDiv.innerHTML = `
                            <div style="background: var(--bg-dark); padding: 20px; border-radius: 8px; border-left: 4px solid var(--accent-gold); color: #e0e0e0;">
                                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                                    <span style="font-size: 1.5em; margin-right: 10px;">✅</span>
                                    <h3 style="margin: 0; color: var(--accent-bright);">Query Executed Successfully</h3>
                                </div>
                                <p style="color: #a0a0a0; margin-bottom: 10px;">Returned ${resultsCount} result${resultsCount !== 1 ? 's' : ''}.</p>
                                <details style="margin-top: 15px;">
                                    <summary style="cursor: pointer; color: var(--accent-bright); font-weight: 600;">View Results (${resultsCount} items)</summary>
                                    <div style="margin-top: 10px; max-height: 400px; overflow-y: auto;">
                                        <pre style="background: var(--bg-gray); padding: 15px; border-radius: 4px; font-size: 0.9em; overflow-x: auto; color: #d0d0d0;">${JSON.stringify(data.results, null, 2)}</pre>
                                    </div>
                                </details>
                            </div>
                        `;
                        resultsDiv.classList.remove('empty');
                    } else {
                        resultsDiv.innerHTML = `
                            <div class="success-message">${data.message || 'Query executed successfully but returned no results'}</div>
                        `;
                        resultsDiv.classList.add('empty');
                    }
                } else {
                    resultsDiv.innerHTML = `<div class="error-message">${data.error || 'Query failed'}</div>`;
                    resultsDiv.classList.add('empty');
                }
            } catch (error) {
                console.error('Error executing query:', error);
                resultsDiv.innerHTML = `<div class="error-message">Error: ${error.message || 'Unknown error'}</div>`;
                resultsDiv.classList.add('empty');
            }
        }

        // Graph visualization removed - now using LLM to answer questions directly

        // Clear query
        function clearQuery() {
            document.getElementById('cypherQuery').value = '';
            document.getElementById('nlQuery').value = '';
            document.getElementById('queryResults').innerHTML = 'Query results will appear here...';
            document.getElementById('queryResults').classList.add('empty');
        }
        
        // Allow Enter key to submit natural language query; init auth state
        document.addEventListener('DOMContentLoaded', function() {
            // Enter-to-send for the Ask composer is wired via askComposerKey in the markup.
            refreshAuthState();
        });

        // Refresh the active stage's data (rail sync button)
        function refreshAll() {
            const active = document.querySelector('.rail-item.active');
            const tabIndex = active ? parseInt(active.getAttribute('data-tab'), 10) : 0;
            const btn = document.getElementById('refreshBtn');
            if (btn) { btn.classList.add('spinning'); setTimeout(() => btn.classList.remove('spinning'), 600); }
            if (tabIndex === 0) loadDownloadStatus();
            else if (tabIndex === 1) loadTranscriptions();
        }

        // Utility function
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Initialize — open the tab matching the URL Flask served (deep-link support).
        switchTab((typeof window.INITIAL_TAB === 'number') ? window.INITIAL_TAB : 0, false);
        refreshAuthState();

        // ── Quiz ──────────────────────────────────────────────────────────────

        const qzCfg = { type: 'facts', difficulty: 'easy', mode: 'random', count: 10 };
        const qzSess = { questions: [], idx: 0, score: 0, results: [], wrongQuestions: [] };
        let qzUser = null;  // populated from auth state

        function quizPick(btn) {
            const g = btn.dataset.g, v = btn.dataset.v;
            btn.closest('.quiz-opts').querySelectorAll('.quiz-opt').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (g === 'type')  qzCfg.type       = v;
            if (g === 'diff')  qzCfg.difficulty  = v;
            if (g === 'mode')  qzCfg.mode        = v;
            if (g === 'count') qzCfg.count       = parseInt(v, 10);
        }

        async function initQuizTab() {
            // Load question counts
            try {
                const r = await fetch('/api/quiz/count');
                const d = await r.json();
                const wrap = document.getElementById('quizCounts');
                const types = ['facts_easy','facts_hard','content_easy','content_hard'];
                const labels = {'facts_easy':'Facts Easy','facts_hard':'Facts Hard','content_easy':'Content Easy','content_hard':'Content Hard'};
                wrap.innerHTML = types.map(k => {
                    const n = (d.counts || {})[k] || 0;
                    return `<span class="quiz-count-badge ${n>0?'has-q':'no-q'}">${labels[k]}: ${n}</span>`;
                }).join('');
            } catch(e) {}

            // Load user stats if logged in
            const me = await fetch('/api/auth/me').then(r=>r.json()).catch(()=>({success:false}));
            qzUser = (me.success && me.user) ? me.user : null;

            const skipRow = document.getElementById('skipAnsweredRow');
            const addWrap = document.getElementById('addQFormWrap');
            const statsDiv = document.getElementById('quizUserStats');
            const adminSec = document.getElementById('quizAdminSection');

            if (qzUser) {
                skipRow.style.display = '';
                addWrap.style.display = '';
                loadQuizStats();
                if (qzUser.is_admin) { adminSec.style.display = ''; loadPendingQuestions(); }
            } else {
                skipRow.style.display = 'none';
                addWrap.style.display = 'none';
                statsDiv.style.display = 'none';
                adminSec.style.display = 'none';
            }
        }

        async function loadQuizStats() {
            try {
                const r = await fetch('/api/quiz/stats');
                const d = await r.json();
                if (!d.success) return;
                const s = d.stats;
                const pct = s.total_attempts > 0 ? Math.round(s.total_correct / s.total_attempts * 100) : 0;
                document.getElementById('quizStatsGrid').innerHTML = `
                    <div class="quiz-stat-box"><div class="quiz-stat-val">${s.total_attempts}</div><div class="quiz-stat-lbl">Total Attempts</div></div>
                    <div class="quiz-stat-box"><div class="quiz-stat-val">${pct}%</div><div class="quiz-stat-lbl">Accuracy</div></div>
                    <div class="quiz-stat-box"><div class="quiz-stat-val">${s.questions_attempted}</div><div class="quiz-stat-lbl">Questions Seen</div></div>
                `;
                document.getElementById('quizUserStats').style.display = '';
            } catch(e) {}
        }

        async function loadPendingQuestions() {
            try {
                const r = await fetch('/api/quiz/admin/pending');
                const d = await r.json();
                if (!d.success) return;
                const list = document.getElementById('quizPendingList');
                document.getElementById('pendingCount').textContent = `(${d.questions.length})`;
                if (!d.questions.length) { list.innerHTML = '<p style="color:#606060;">No pending questions.</p>'; return; }
                list.innerHTML = d.questions.map(q => `
                    <div class="quiz-pending-item" id="pq-${q.id}">
                        <div class="q-meta">[${q.type}/${q.difficulty}] submitted by ${escapeHtml(q.submitted_by||'?')}</div>
                        <div class="q-text">${escapeHtml(q.question_text)}</div>
                        <div style="font-size:0.8em;color:#a0a0a0;margin:4px 0;">${(q.options||[]).map(o=>`<em>${escapeHtml(o)}</em>`).join(' / ')} → <strong style="color:#6fcf97;">${escapeHtml(q.correct_answer)}</strong></div>
                        <div class="q-actions">
                            <button class="btn btn-primary" style="padding:4px 12px;font-size:0.8em;" onclick="reviewQuestion(${q.id},'approve')">Approve</button>
                            <button class="btn btn-secondary" style="padding:4px 12px;font-size:0.8em;" onclick="reviewQuestion(${q.id},'reject')">Reject</button>
                        </div>
                    </div>
                `).join('');
            } catch(e) {}
        }

        async function reviewQuestion(qid, action) {
            const r = await fetch('/api/quiz/admin/review', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({question_id: qid, action})
            });
            const d = await r.json();
            if (d.success) {
                const el = document.getElementById(`pq-${qid}`);
                if (el) el.remove();
            }
        }

        async function startQuiz(questionsOverride) {
            const loading = `<div style="text-align:center;padding:40px;color:#a0a0a0;"><div class="loading"></div> Loading questions...</div>`;
            document.getElementById('quizSetup').style.display = 'none';
            document.getElementById('quizQuestion').style.display = '';
            document.getElementById('quizSummary').style.display = 'none';
            document.getElementById('qOptions').innerHTML = loading;

            let questions = questionsOverride;
            if (!questions) {
                const skip = qzUser && document.getElementById('skipAnswered')?.checked;
                const url = `/api/quiz/questions?type=${qzCfg.type}&difficulty=${qzCfg.difficulty}&mode=${qzCfg.mode}&count=${qzCfg.count}&skip_answered=${skip?'true':'false'}`;
                const r = await fetch(url);
                const d = await r.json();
                questions = d.success ? d.questions : [];
            }

            if (!questions.length) {
                document.getElementById('quizSetup').style.display = '';
                document.getElementById('quizQuestion').style.display = 'none';
                toast.info('No questions available for this selection. Try different settings or generate questions first.');
                return;
            }

            qzSess.questions  = questions;
            qzSess.idx        = 0;
            qzSess.score      = 0;
            qzSess.results    = [];
            qzSess.wrongQuestions = [];
            renderDots();
            showQuestion(0);
        }

        function renderDots() {
            const n = qzSess.questions.length;
            document.getElementById('qDots').innerHTML = Array.from({length: n}, (_, i) => {
                let cls = 'quiz-dot';
                if (i < qzSess.idx) {
                    const r = qzSess.results[i];
                    cls += r ? ' done-right' : ' done-wrong';
                } else if (i === qzSess.idx) {
                    cls += ' current';
                }
                return `<span class="${cls}"></span>`;
            }).join('');
        }

        function showQuestion(idx) {
            const q = qzSess.questions[idx];
            const n = qzSess.questions.length;
            document.getElementById('qProgressText').textContent = `${idx + 1} / ${n}`;
            document.getElementById('qScoreText').textContent = `Score: ${qzSess.score}`;
            document.getElementById('qText').textContent = q.question_text;
            document.getElementById('qFeedback').style.display = 'none';
            document.getElementById('qNextBtn').style.display = 'none';
            document.getElementById('qOptions').innerHTML = (q.options || []).map(opt =>
                `<button class="quiz-opt-btn" onclick="submitAnswer(this, ${JSON.stringify(opt)})">${escapeHtml(opt)}</button>`
            ).join('');
        }

        async function submitAnswer(btn, answer) {
            // Disable all option buttons
            document.querySelectorAll('.quiz-opt-btn').forEach(b => b.disabled = true);

            const q = qzSess.questions[qzSess.idx];
            let correct, correctAnswer, explanation;

            // Always verify with server to get correct answer + log attempt
            try {
                const r = await fetch('/api/quiz/answer', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({question_id: q.id, answer})
                });
                const d = await r.json();
                correct = d.correct;
                correctAnswer = d.correct_answer;
                explanation = d.explanation || '';
            } catch(e) {
                correct = false; correctAnswer = ''; explanation = '';
            }

            // Highlight buttons
            document.querySelectorAll('.quiz-opt-btn').forEach(b => {
                const bText = b.textContent.trim();
                if (bText === (correctAnswer || '').trim()) b.classList.add('correct');
                else if (b === btn && !correct) b.classList.add('wrong');
            });

            // Feedback
            const fb = document.getElementById('qFeedback');
            fb.className = `quiz-feedback ${correct ? 'correct' : 'wrong'}`;
            fb.innerHTML = `<strong>${correct ? '✓ Correct!' : '✗ Wrong'}</strong>${explanation ? ' — ' + escapeHtml(explanation) : ''}`;
            fb.style.display = '';

            if (correct) qzSess.score++;
            else qzSess.wrongQuestions.push({...q});
            qzSess.results.push(correct);
            renderDots();
            document.getElementById('qNextBtn').style.display = '';
        }

        function nextQuestion() {
            qzSess.idx++;
            if (qzSess.idx >= qzSess.questions.length) {
                showSummary();
            } else {
                showQuestion(qzSess.idx);
            }
        }

        function showSummary() {
            document.getElementById('quizQuestion').style.display = 'none';
            document.getElementById('quizSummary').style.display = '';
            const n = qzSess.questions.length;
            const s = qzSess.score;
            const pct = Math.round(s / n * 100);
            document.getElementById('qFinalScore').textContent = `${s} / ${n}`;
            document.getElementById('qFinalPct').textContent = `${pct}% accuracy`;
            const stars = pct >= 90 ? '⭐⭐⭐' : pct >= 60 ? '⭐⭐' : '⭐';
            document.getElementById('qStars').textContent = stars;
            const retryBtn = document.getElementById('retryWrongBtn');
            if (qzSess.wrongQuestions.length > 0) {
                retryBtn.style.display = '';
                retryBtn.textContent = `Retry Wrong (${qzSess.wrongQuestions.length})`;
            } else {
                retryBtn.style.display = 'none';
            }
            loadQuizStats();
        }

        function retryWrong() {
            startQuiz([...qzSess.wrongQuestions]);
        }

        function showQuizSetup() {
            document.getElementById('quizSummary').style.display = 'none';
            document.getElementById('quizQuestion').style.display = 'none';
            document.getElementById('quizSetup').style.display = '';
            initQuizTab();
        }

        function toggleAddForm() {
            const f = document.getElementById('addQForm');
            f.style.display = f.style.display === 'none' ? '' : 'none';
        }

        async function submitAddQuestion() {
            const opts = [0,1,2,3].map(i => (document.getElementById(`aqOpt${i}`)?.value||'').trim()).filter(Boolean);
            const payload = {
                type:          document.getElementById('aqType').value,
                difficulty:    document.getElementById('aqDiff').value,
                question_text: (document.getElementById('aqText').value||'').trim(),
                options:       opts,
                correct_answer:(document.getElementById('aqCorrect').value||'').trim(),
                explanation:   (document.getElementById('aqExplain').value||'').trim(),
            };
            const errEl = document.getElementById('aqError');
            if (!payload.question_text) { errEl.textContent='Question text required'; errEl.style.display=''; return; }
            if (opts.length < 2) { errEl.textContent='At least 2 options required'; errEl.style.display=''; return; }
            if (!payload.correct_answer) { errEl.textContent='Correct answer required'; errEl.style.display=''; return; }
            errEl.style.display = 'none';
            try {
                const r = await fetch('/api/quiz/add-question', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify(payload)
                });
                const d = await r.json();
                if (d.success) {
                    toast.success(d.message);
                    toggleAddForm();
                    initQuizTab();
                } else {
                    errEl.textContent = d.error || 'Failed';
                    errEl.style.display = '';
                }
            } catch(e) { errEl.textContent = 'Network error'; errEl.style.display = ''; }
        }
