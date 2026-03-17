document.addEventListener("DOMContentLoaded", function () {

    // ─── Elements
    const chatContainer   = document.getElementById("chatContainer");
    const userInput       = document.getElementById("userInput");
    const sendBtn         = document.getElementById("sendBtn");
    const micButton       = document.getElementById("micButton");
    const stopRecording   = document.getElementById("stopRecording");
    const recordingBar    = document.getElementById("recordingBar");
    const responseAudio   = document.getElementById("responseAudio");
    const voiceToggle     = document.getElementById("voiceToggle");
    const audioToggle     = document.getElementById("audioToggle");
    const emotionToggle   = document.getElementById("emotionToggle");
    const apiNotice       = document.getElementById("apiNotice");
    const newChatBtn      = document.getElementById("newChatBtn");
    const newChatBtnMobile= document.getElementById("newChatBtnMobile");
    const convList        = document.getElementById("convList");
    const modelSelect     = document.getElementById("modelSelect");
    const sidebarToggle   = document.getElementById("sidebarToggle");
    const sidebar         = document.getElementById("sidebar");
    const sidebarOverlay  = document.getElementById("sidebarOverlay");
    const topbarTitle     = document.getElementById("topbarTitle");

    // ─── State
    let enableVoiceInput  = true;
    let enableVoiceOutput = false;
    let enableEmotion     = true;
    let currentConvId     = null;
    let mediaRecorder;
    let audioChunks       = [];
    let isRecording       = false;

    // ─── Sidebar toggle (mobile)
    function openSidebar()  { sidebar.classList.add('open'); sidebarOverlay.classList.add('open'); }
    function closeSidebar() { sidebar.classList.remove('open'); sidebarOverlay.classList.remove('open'); }
    sidebarToggle.addEventListener('click', openSidebar);
    sidebarOverlay.addEventListener('click', closeSidebar);

    // ─── Auto-resize textarea
    userInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });

    // ─── Send on Enter (not Shift+Enter)
    userInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });
    sendBtn.addEventListener('click', handleSend);

    // ─── Feature toggles
    voiceToggle.addEventListener('click', function () {
        enableVoiceInput = !enableVoiceInput;
        this.classList.toggle('active', enableVoiceInput);
    });
    audioToggle.addEventListener('click', function () {
        enableVoiceOutput = !enableVoiceOutput;
        this.classList.toggle('active', enableVoiceOutput);
    });
    emotionToggle.addEventListener('click', function () {
        enableEmotion = !enableEmotion;
        this.classList.toggle('active', enableEmotion);
        document.querySelectorAll('.emotion-badge').forEach(el => {
            el.style.display = enableEmotion ? 'inline-block' : 'none';
        });
    });

    // ─── New chat
    function startNewChat() {
        currentConvId = null;
        chatContainer.innerHTML = '';
        chatContainer.appendChild(createWelcome());
        document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
        topbarTitle.textContent = 'Sol Space';
        if (window.innerWidth < 769) closeSidebar();
    }
    newChatBtn.addEventListener('click', startNewChat);
    newChatBtnMobile.addEventListener('click', startNewChat);

    // ─── Welcome block
    function createWelcome() {
        const el = document.createElement('div');
        el.className = 'welcome-block';
        el.id = 'welcomeBlock';
        el.innerHTML = `
            <div class="welcome-logo">Sol</div>
            <h2 class="welcome-heading">How can I help you today?</h2>
            <p class="welcome-sub">A safe space to think, feel, and talk things through.</p>
        `;
        return el;
    }

    // ─── Load conversations list
    function loadConversations() {
        fetch('/api/conversations')
            .then(r => r.json())
            .then(convs => {
                convList.innerHTML = '';
                convs.forEach(c => {
                    const item = createConvItem(c);
                    convList.appendChild(item);
                });
            })
            .catch(err => console.error('Error loading conversations:', err));
    }

    function createConvItem(conv) {
        const item = document.createElement('div');
        item.className = 'conv-item';
        item.dataset.id = conv.id;
        if (conv.id === currentConvId) item.classList.add('active');

        const title = document.createElement('span');
        title.className = 'conv-item-title';
        title.textContent = conv.title;

        const del = document.createElement('button');
        del.className = 'conv-delete';
        del.innerHTML = '<i class="fas fa-trash"></i>';
        del.title = 'Delete';
        del.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteConversation(conv.id, item);
        });

        item.appendChild(title);
        item.appendChild(del);

        item.addEventListener('click', () => loadConversation(conv.id));
        return item;
    }

    function deleteConversation(id, itemEl) {
        fetch(`/api/conversations/${id}`, { method: 'DELETE' })
            .then(() => {
                itemEl.remove();
                if (currentConvId === id) startNewChat();
            })
            .catch(err => console.error('Error deleting:', err));
    }

    function loadConversation(id) {
        currentConvId = id;
        chatContainer.innerHTML = '';

        fetch(`/api/conversations/${id}/messages`)
            .then(r => r.json())
            .then(messages => {
                if (messages.length === 0) {
                    chatContainer.appendChild(createWelcome());
                } else {
                    messages.forEach(m => addMessage(m.content, m.role, m.timestamp, m.emotion, null));
                }
                // Update sidebar active state
                document.querySelectorAll('.conv-item').forEach(el => {
                    el.classList.toggle('active', parseInt(el.dataset.id) === id);
                });
                // Update topbar title
                const activeItem = document.querySelector(`.conv-item[data-id="${id}"] .conv-item-title`);
                if (activeItem) topbarTitle.textContent = activeItem.textContent;

                scrollToBottom();
                if (window.innerWidth < 769) closeSidebar();
            })
            .catch(err => console.error('Error loading messages:', err));
    }

    // ─── Render a message
    function formatContent(text) {
        // Escape HTML
        let escaped = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        // Code blocks ```lang\n...```
        escaped = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code>${code.trim()}</code></pre>`;
        });
        // Inline code `...`
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Bold **...**
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Line breaks
        escaped = escaped.replace(/\n/g, '<br>');
        return escaped;
    }

    function addMessage(content, role, timestamp, emotion, audioData) {
        // Remove welcome block
        const wb = document.getElementById('welcomeBlock');
        if (wb) wb.remove();

        const row = document.createElement('div');
        row.className = `msg-row ${role}`;

        const inner = document.createElement('div');
        inner.className = 'msg-inner';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = role === 'user' ? 'You' : 'Sol';

        const wrap = document.createElement('div');
        wrap.className = 'msg-content-wrap';

        const name = document.createElement('div');
        name.className = 'msg-name';
        name.textContent = role === 'user' ? 'You' : 'Sol';

        const body = document.createElement('div');
        body.className = 'msg-content';

        // Emotion badge
        if (emotion && enableEmotion && role === 'user') {
            const icons = { happy: '😊', sad: '😢', angry: '😠', fearful: '😨', surprised: '😲', neutral: '' };
            if (icons[emotion]) {
                const badge = document.createElement('span');
                badge.className = 'emotion-badge';
                badge.textContent = icons[emotion];
                body.appendChild(badge);
            }
        }

        const contentSpan = document.createElement('span');
        contentSpan.innerHTML = formatContent(content);
        body.appendChild(contentSpan);

        const timeEl = document.createElement('div');
        timeEl.className = 'msg-time';
        if (timestamp) {
            const d = new Date(timestamp);
            timeEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        wrap.appendChild(name);
        wrap.appendChild(body);
        wrap.appendChild(timeEl);

        // Audio playback button
        if (audioData && role === 'assistant') {
            const actions = document.createElement('div');
            actions.className = 'msg-actions';
            const playBtn = document.createElement('button');
            playBtn.className = 'audio-btn';
            playBtn.innerHTML = '<i class="fas fa-volume-up"></i> Play';
            playBtn.addEventListener('click', () => {
                responseAudio.src = audioData;
                responseAudio.play();
            });
            actions.appendChild(playBtn);
            wrap.appendChild(actions);
        }

        inner.appendChild(avatar);
        inner.appendChild(wrap);
        row.appendChild(inner);
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function addTypingIndicator() {
        const row = document.createElement('div');
        row.className = 'typing-row';
        row.id = 'typingIndicator';
        row.innerHTML = `
            <div class="typing-inner">
                <div class="msg-avatar assistant">Sol</div>
                <div class="typing-dots"><span></span><span></span><span></span></div>
            </div>`;
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const el = document.getElementById('typingIndicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // ─── Send message
    function handleSend() {
        const text = userInput.value.trim();
        if (!text) return;
        userInput.value = '';
        userInput.style.height = 'auto';
        sendMessage(text, null);
    }

    function sendMessage(message, voiceData) {
        if (!message && !voiceData) return;

        if (message && message !== 'Voice input') {
            addMessage(message, 'user', new Date().toISOString(), null, null);
        }

        addTypingIndicator();

        const body = { model: modelSelect.value };
        if (message) body.message = message;
        if (voiceData) body.voice_data = voiceData;
        if (currentConvId) body.conversation_id = currentConvId;
        const persona = window._getPersona ? window._getPersona() : {};
        if (persona.name)   body.persona_name   = persona.name;
        if (persona.prompt) body.system_prompt  = persona.prompt;

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(r => {
            if (!r.ok) throw new Error('Network error');
            return r.json();
        })
        .then(data => {
            removeTypingIndicator();

            if (data.error) {
                addMessage(data.error, 'assistant', new Date().toISOString(), null, null);
                return;
            }

            // Update conversation tracking
            if (data.conversation_id && data.conversation_id !== currentConvId) {
                currentConvId = data.conversation_id;
                loadConversations();  // Refresh sidebar list
            } else if (data.conversation_id) {
                // Update title in sidebar if it changed
                const titleEl = document.querySelector(`.conv-item[data-id="${data.conversation_id}"] .conv-item-title`);
                if (titleEl && data.conversation_title) {
                    titleEl.textContent = data.conversation_title;
                    topbarTitle.textContent = data.conversation_title;
                }
                // Mark active
                document.querySelectorAll('.conv-item').forEach(el => {
                    el.classList.toggle('active', parseInt(el.dataset.id) === currentConvId);
                });
            }

            // Show/hide user emotion on the last user message
            if (data.emotion && enableEmotion) {
                const userRows = document.querySelectorAll('.msg-row.user');
                const lastUser = userRows[userRows.length - 1];
                if (lastUser) {
                    const icons = { happy: '😊', sad: '😢', angry: '😠', fearful: '😨', surprised: '😲' };
                    if (icons[data.emotion]) {
                        const badge = lastUser.querySelector('.emotion-badge');
                        if (!badge) {
                            const span = document.createElement('span');
                            span.className = 'emotion-badge';
                            span.textContent = icons[data.emotion];
                            const contentSpan = lastUser.querySelector('.msg-content');
                            if (contentSpan) contentSpan.prepend(span);
                        }
                    }
                }
            }

            addMessage(data.message, 'assistant', data.timestamp, null, data.audio);

            // API notice
            apiNotice.style.display = data.local_mode ? 'flex' : 'none';

            // Autoplay audio
            if (data.audio && enableVoiceOutput) {
                responseAudio.src = data.audio;
                responseAudio.play();
            }
        })
        .catch(err => {
            removeTypingIndicator();
            addMessage("Something went wrong. Please try again.", 'assistant', new Date().toISOString(), null, null);
            console.error(err);
        });
    }

    // ─── Voice recording
    function startRecording() {
        if (isRecording || !enableVoiceInput) return;
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                isRecording = true;
                recordingBar.classList.add('active');
                micButton.classList.add('recording');

                try {
                    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                } catch (e) {
                    mediaRecorder = new MediaRecorder(stream);
                }
                audioChunks = [];

                mediaRecorder.addEventListener('dataavailable', e => {
                    if (e.data.size > 0) audioChunks.push(e.data);
                });

                mediaRecorder.addEventListener('stop', () => {
                    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                    const reader = new FileReader();
                    reader.onloadend = () => sendMessage('Voice input', reader.result);
                    reader.readAsDataURL(blob);
                    stream.getTracks().forEach(t => t.stop());
                    isRecording = false;
                    recordingBar.classList.remove('active');
                    micButton.classList.remove('recording');
                });

                mediaRecorder.start(100);
                setTimeout(() => { if (isRecording) stopRecordingFn(); }, 5000);
            })
            .catch(err => {
                console.error('Mic error:', err);
                isRecording = false;
            });
    }

    function stopRecordingFn() {
        if (mediaRecorder && isRecording) mediaRecorder.stop();
    }

    micButton.addEventListener('click', () => isRecording ? stopRecordingFn() : startRecording());
    stopRecording.addEventListener('click', stopRecordingFn);

    // ─── Init
    loadConversations();
    userInput.focus();
});

// ─── Persona Settings ────────────────────────────────────────────────
(function () {
    const settingsBtn   = document.getElementById('settingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const settingsClose = document.getElementById('settingsClose');
    const settingsSave  = document.getElementById('settingsSave');
    const settingsReset = document.getElementById('settingsReset');
    const personaNameEl = document.getElementById('personaName');
    const personaPromptEl = document.getElementById('personaPrompt');
    const presetBtns    = document.querySelectorAll('.preset-btn');

    // Load from localStorage
    function loadPersona() {
        return {
            name:   localStorage.getItem('sol_persona_name')   || '',
            prompt: localStorage.getItem('sol_persona_prompt') || ''
        };
    }

    function savePersona(name, prompt) {
        localStorage.setItem('sol_persona_name',   name);
        localStorage.setItem('sol_persona_prompt', prompt);
    }

    function applyPersona(name, prompt) {
        // Update avatar labels
        const label = name || 'Sol';
        document.querySelectorAll('.msg-row.assistant .msg-avatar').forEach(el => el.textContent = label);
        document.querySelectorAll('.msg-row.assistant .msg-name').forEach(el => el.textContent = label);
        document.querySelector('.welcome-logo') && (document.querySelector('.welcome-logo').textContent = label.slice(0, 3));
        document.querySelector('.welcome-heading') && (document.querySelector('.welcome-heading').textContent = `How can I help you today?`);
    }

    function openModal() {
        const p = loadPersona();
        personaNameEl.value   = p.name;
        personaPromptEl.value = p.prompt;
        settingsModal.classList.add('open');
        updatePresetSelection();
    }

    function closeModal() { settingsModal.classList.remove('open'); }

    function updatePresetSelection() {
        const currentPrompt = personaPromptEl.value.trim();
        presetBtns.forEach(btn => {
            btn.classList.toggle('selected', btn.dataset.prompt === currentPrompt);
        });
    }

    settingsBtn.addEventListener('click', openModal);
    settingsClose.addEventListener('click', closeModal);
    settingsModal.addEventListener('click', (e) => { if (e.target === settingsModal) closeModal(); });

    presetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            personaNameEl.value   = btn.dataset.name;
            personaPromptEl.value = btn.dataset.prompt;
            updatePresetSelection();
        });
    });

    personaPromptEl.addEventListener('input', updatePresetSelection);

    settingsSave.addEventListener('click', () => {
        const name   = personaNameEl.value.trim();
        const prompt = personaPromptEl.value.trim();
        savePersona(name, prompt);
        applyPersona(name, prompt);
        closeModal();
        // Visual confirmation
        const btn = settingsSave;
        const orig = btn.textContent;
        btn.textContent = 'Saved!';
        setTimeout(() => btn.textContent = orig, 1500);
    });

    settingsReset.addEventListener('click', () => {
        personaNameEl.value   = '';
        personaPromptEl.value = '';
        updatePresetSelection();
    });

    // Apply on page load
    const p = loadPersona();
    if (p.name || p.prompt) applyPersona(p.name, p.prompt);

    // Hook into sendMessage to attach persona data
    const origSendMessage = window._sendMessage;

    // Patch: make persona available to the sendMessage function
    window._getPersona = function () {
        return loadPersona();
    };
})();
