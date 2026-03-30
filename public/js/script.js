document.addEventListener("DOMContentLoaded", () => {
    const state = {
        csrfToken: "",
        user: null,
        currentConvId: null,
        currentMode: "companion",
        enableVoiceInput: true,
        enableVoiceOutput: false,
        isRecording: false,
        mediaRecorder: null,
        audioChunks: [],
        preferences: {},
        memories: [],
        editingMemoryId: null,
        regenerateModelOverride: "",
    };

    const authShell = document.getElementById("authShell");
    const appShell = document.getElementById("appShell");
    const authForm = document.getElementById("authForm");
    const authEmail = document.getElementById("authEmail");
    const authPassword = document.getElementById("authPassword");
    const authError = document.getElementById("authError");
    const authHint = document.getElementById("authHint");
    const authSubmit = document.getElementById("authSubmit");
    const authTabs = document.querySelectorAll(".auth-tab");
    const accountName = document.getElementById("accountName");
    const accountEmail = document.getElementById("accountEmail");
    const profileBtn = document.getElementById("profileBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const convList = document.getElementById("convList");
    const memoryList = document.getElementById("memoryList");
    const memoryHubBtn = document.getElementById("memoryHubBtn");
    const memoryHubModal = document.getElementById("memoryHubModal");
    const memoryHubClose = document.getElementById("memoryHubClose");
    const quickControlsBtn = document.getElementById("quickControlsBtn");
    const quickControlsBtnMobile = document.getElementById("quickControlsBtnMobile");
    const quickControlsModal = document.getElementById("quickControlsModal");
    const quickControlsClose = document.getElementById("quickControlsClose");
    const topbarTitle = document.getElementById("topbarTitle");
    const newChatBtn = document.getElementById("newChatBtn");
    const newChatBtnMobile = document.getElementById("newChatBtnMobile");
    const newMemoryBtn = document.getElementById("newMemoryBtn");

    const modeButtons = document.querySelectorAll(".mode-btn");
    const modeBadge = document.getElementById("modeBadge");
    const composerTip = document.getElementById("composerTip");
    const welcomeHeading = document.getElementById("welcomeHeading");
    const welcomeSub = document.getElementById("welcomeSub");
    const chatContainer = document.getElementById("chatContainer");
    const apiNotice = document.getElementById("apiNotice");
    const apiNoticeText = document.getElementById("apiNoticeText");
    const modelSelect = document.getElementById("modelSelect");
    const userInput = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    const micButton = document.getElementById("micButton");
    const stopRecording = document.getElementById("stopRecording");
    const recordingBar = document.getElementById("recordingBar");
    const responseAudio = document.getElementById("responseAudio");
    const voiceToggle = document.getElementById("voiceToggle");
    const audioToggle = document.getElementById("audioToggle");

    const settingsBtn = document.getElementById("settingsBtn");
    const profileModal = document.getElementById("profileModal");
    const profileClose = document.getElementById("profileClose");
    const profileSave = document.getElementById("profileSave");
    const profileName = document.getElementById("profileName");
    const profileAbout = document.getElementById("profileAbout");
    const profileError = document.getElementById("profileError");
    const settingsModal = document.getElementById("settingsModal");
    const settingsClose = document.getElementById("settingsClose");
    const settingsSave = document.getElementById("settingsSave");
    const settingsReset = document.getElementById("settingsReset");
    const personaNameEl = document.getElementById("personaName");
    const personaPromptEl = document.getElementById("personaPrompt");
    const voiceProviderEl = document.getElementById("voiceProvider");
    const voiceNameEl = document.getElementById("voiceName");
    const presetButtons = document.querySelectorAll(".preset-btn");

    const memoryModal = document.getElementById("memoryModal");
    const memoryClose = document.getElementById("memoryClose");
    const memorySave = document.getElementById("memorySave");
    const memoryDelete = document.getElementById("memoryDelete");
    const memoryTitle = document.getElementById("memoryTitle");
    const memoryContent = document.getElementById("memoryContent");
    const memoryError = document.getElementById("memoryError");

    const importBtn = document.getElementById("importBtn");
    const importModal = document.getElementById("importModal");
    const importClose = document.getElementById("importClose");
    const importCancel = document.getElementById("importCancel");
    const importStart = document.getElementById("importStart");
    const importFile = document.getElementById("importFile");
    const importError = document.getElementById("importError");

    let authMode = "login";

    function openSidebar() {
        sidebar.classList.add("open");
        sidebarOverlay.classList.add("open");
        document.body.classList.add("sidebar-open");
    }

    function closeSidebar() {
        sidebar.classList.remove("open");
        sidebarOverlay.classList.remove("open");
        document.body.classList.remove("sidebar-open");
    }

    function updateAuthMode(nextMode) {
        authMode = nextMode;
        authTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.authMode === nextMode));
        authSubmit.textContent = nextMode === "login" ? "Log in" : "Create account";
        authHint.textContent = nextMode === "login"
            ? "Your sessions stay yours. Always."
            : "Passwords must be at least 8 characters.";
        authPassword.autocomplete = nextMode === "login" ? "current-password" : "new-password";
        authError.textContent = "";
    }

    function getCurrentPreference() {
        return state.preferences[state.currentMode] || {
            persona_name: "",
            system_prompt: "",
            voice_provider: "browser",
            voice_name: "",
        };
    }

    function getEffectivePersonaName() {
        return getCurrentPreference().persona_name || (state.currentMode === "coding" ? "Sol Code" : "Sol");
    }

    function applyPersona() {
        const label = getEffectivePersonaName();
        document.querySelectorAll(".msg-row.assistant .msg-avatar, .msg-row.assistant .msg-name").forEach((el) => {
            el.textContent = label;
        });
        const logo = document.querySelector(".welcome-logo");
        if (logo) {
            logo.textContent = label.slice(0, 3);
        }
    }

    async function apiFetch(url, options = {}) {
        const opts = { ...options };
        opts.headers = { ...(opts.headers || {}) };
        if (opts.body && !(opts.body instanceof FormData) && !opts.headers["Content-Type"]) {
            opts.headers["Content-Type"] = "application/json";
        }
        if (["POST", "PATCH", "PUT", "DELETE"].includes((opts.method || "GET").toUpperCase())) {
            opts.headers["X-CSRF-Token"] = state.csrfToken;
        }

        let response;
        try {
            response = await fetch(url, opts);
        } catch (error) {
            throw new Error("Network error reaching the server");
        }

        const rawText = await response.text();
        let data = {};
        try {
            data = rawText ? JSON.parse(rawText) : {};
        } catch (error) {
            data = {};
        }
        if (!response.ok) {
            throw new Error(data.error || rawText || `Request failed (${response.status})`);
        }
        return data;
    }

    function createWelcome() {
        const block = document.createElement("div");
        block.className = "welcome-block";
        block.id = "welcomeBlock";

        const logo = document.createElement("div");
        logo.className = "welcome-logo";
        logo.textContent = getEffectivePersonaName().slice(0, 3);

        const heading = document.createElement("h2");
        heading.className = "welcome-heading";
        heading.textContent = state.currentMode === "coding" ? "What are we building?" : "Your mind, amplified.";

        const sub = document.createElement("p");
        sub.className = "welcome-sub";
        sub.textContent = state.currentMode === "coding"
            ? "Debug, review architecture, draft code, and plan production launches."
            : "Persistent memory, private conversations, and a workspace that keeps up with you.";

        block.appendChild(logo);
        block.appendChild(heading);
        block.appendChild(sub);
        return block;
    }

    function updateModeUI() {
        const isCoding = state.currentMode === "coding";
        modeBadge.textContent = isCoding ? "Coding Mode" : "Chat Mode";
        composerTip.textContent = isCoding
            ? "Focused on debugging, architecture, implementation, and code review."
            : "Private chat, ideas, and everyday chaos.";
        welcomeHeading.textContent = isCoding ? "What are we building?" : "Your mind, amplified.";
        welcomeSub.textContent = isCoding
            ? "Debug, review architecture, draft code, and plan production launches."
            : "Persistent memory, private conversations, and a workspace that keeps up with you.";
        userInput.placeholder = isCoding ? "Paste code or ask a coding question..." : "Message Sol...";
        audioToggle.disabled = isCoding;
        audioToggle.classList.toggle("disabled", isCoding);
        if (isCoding) {
            state.enableVoiceOutput = false;
            audioToggle.classList.remove("active");
        }
        topbarTitle.textContent = isCoding ? "Coding" : "Sol Space";
        applyPersona();
    }

    function stopSpeech() {
        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }
    }

    function speakText(text) {
        if (!("speechSynthesis" in window)) {
            return;
        }
        stopSpeech();
        const preference = getCurrentPreference();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1;
        utterance.pitch = 1;
        if ((preference.voice_provider || "browser") === "browser" && preference.voice_name) {
            const voices = window.speechSynthesis.getVoices();
            const matchedVoice = voices.find((voice) => voice.name === preference.voice_name);
            if (matchedVoice) {
                utterance.voice = matchedVoice;
            }
        }
        window.speechSynthesis.speak(utterance);
    }

    function updateAuthenticatedUI() {
        if (state.user) {
            authShell.classList.add("hidden");
            appShell.classList.remove("hidden");
            accountName.textContent = state.user.display_name || "Sol account";
            accountEmail.textContent = state.user.email;
            updateModeUI();
        } else {
            appShell.classList.add("hidden");
            authShell.classList.remove("hidden");
        }
    }

    function formatContent(text) {
        let escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        escaped = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
            const languageClass = lang ? ` class="language-${lang}"` : "";
            return `<pre><code${languageClass}>${code.trim()}</code></pre>`;
        });
        escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        escaped = escaped.replace(/\n/g, "<br>");
        return escaped;
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function clearRegenerateButtons() {
        document.querySelectorAll(".regen-btn").forEach((button) => button.remove());
    }

    async function regenerateLatestResponse() {
        if (!state.currentConvId) {
            return;
        }

        clearRegenerateButtons();
        addTypingIndicator();
        const preference = getCurrentPreference();
        try {
            const data = await apiFetch("/api/chat", {
                method: "POST",
                body: JSON.stringify({
                    conversation_id: state.currentConvId,
                    mode: state.currentMode,
                    model: modelSelect.value,
                    persona_name: preference.persona_name,
                    system_prompt: preference.system_prompt,
                    regenerate: true,
                }),
            });
            removeTypingIndicator();
            await loadConversation(state.currentConvId);
            if (data.local_mode) {
                apiNoticeText.textContent = data.fallback_reason
                    ? `Fallback reason: ${data.fallback_reason}`
                    : "Running in fallback mode because no external model answered.";
                apiNotice.classList.remove("hidden");
            } else {
                apiNotice.classList.add("hidden");
                apiNoticeText.textContent = "Running in fallback mode because no external model answered.";
            }
        } catch (error) {
            removeTypingIndicator();
            addMessage(error.message || "Could not regenerate the reply.", "assistant", new Date().toISOString(), null);
        }
    }

    function addMessage(content, role, timestamp, audioData, memorySuggestion = null, allowRegenerate = false) {
        document.getElementById("welcomeBlock")?.remove();

        const row = document.createElement("div");
        row.className = `msg-row ${role}`;

        const inner = document.createElement("div");
        inner.className = "msg-inner";

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.textContent = role === "user" ? "You" : getEffectivePersonaName();

        const wrap = document.createElement("div");
        wrap.className = "msg-content-wrap";

        const name = document.createElement("div");
        name.className = "msg-name";
        name.textContent = avatar.textContent;

        const body = document.createElement("div");
        body.className = "msg-content";
        const contentSpan = document.createElement("span");
        contentSpan.innerHTML = formatContent(content);
        body.appendChild(contentSpan);

        const timeEl = document.createElement("div");
        timeEl.className = "msg-time";
        if (timestamp) {
            timeEl.textContent = new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }

        wrap.append(name, body, timeEl);

        if (role === "assistant") {
            const actions = document.createElement("div");
            actions.className = "msg-actions";
            const readBtn = document.createElement("button");
            readBtn.className = "audio-btn";
            readBtn.type = "button";
            readBtn.innerHTML = '<i class="fas fa-volume-up"></i> Read aloud';
            readBtn.addEventListener("click", () => {
                if (audioData) {
                    stopSpeech();
                    responseAudio.src = audioData;
                    responseAudio.play();
                    return;
                }
                speakText(content);
            });
            actions.appendChild(readBtn);

            if (allowRegenerate && state.currentConvId) {
                clearRegenerateButtons();
                const regenBtn = document.createElement("button");
                regenBtn.className = "audio-btn regen-btn";
                regenBtn.type = "button";
                regenBtn.innerHTML = '<i class="fas fa-rotate-right"></i> Regenerate';
                regenBtn.addEventListener("click", regenerateLatestResponse);
                actions.appendChild(regenBtn);
            }

            wrap.appendChild(actions);

            if (memorySuggestion?.title && memorySuggestion?.content) {
                const suggestion = document.createElement("div");
                suggestion.className = "memory-suggestion";
                suggestion.innerHTML = `
                    <div class="memory-suggestion-copy">
                        <strong>Suggested memory</strong>
                        <span>${memorySuggestion.title}: ${memorySuggestion.content}</span>
                    </div>
                `;
                const saveButton = document.createElement("button");
                saveButton.className = "audio-btn";
                saveButton.type = "button";
                saveButton.textContent = "Save";
                saveButton.addEventListener("click", async () => {
                    await apiFetch("/api/memories", {
                        method: "POST",
                        body: JSON.stringify({
                            title: memorySuggestion.title,
                            content: memorySuggestion.content,
                        }),
                    });
                    await loadMemories();
                    saveButton.disabled = true;
                    saveButton.textContent = "Saved";
                });
                suggestion.appendChild(saveButton);
                wrap.appendChild(suggestion);
            }
        }

        inner.append(avatar, wrap);
        row.appendChild(inner);
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function addTypingIndicator() {
        const row = document.createElement("div");
        row.className = "typing-row";
        row.id = "typingIndicator";
        row.innerHTML = `
            <div class="typing-inner">
                <div class="msg-avatar assistant">${getEffectivePersonaName()}</div>
                <div class="typing-dots"><span></span><span></span><span></span></div>
            </div>
        `;
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        document.getElementById("typingIndicator")?.remove();
    }

    function startNewChat() {
        state.currentConvId = null;
        chatContainer.innerHTML = "";
        chatContainer.appendChild(createWelcome());
        document.querySelectorAll(".conv-item").forEach((el) => el.classList.remove("active"));
        topbarTitle.textContent = state.currentMode === "coding" ? "Coding" : "Sol Space";
        closeSidebar();
    }

    function renderConversationItem(conversation) {
        const item = document.createElement("div");
        item.className = "conv-item";
        item.dataset.id = conversation.id;
        item.classList.toggle("active", conversation.id === state.currentConvId);
        item.dataset.mode = conversation.mode;

        const title = document.createElement("span");
        title.className = "conv-item-title";
        title.textContent = conversation.title;

        const meta = document.createElement("div");
        meta.className = "conv-item-meta";
        const modeTag = document.createElement("span");
        modeTag.className = "conv-tag";
        modeTag.textContent = conversation.mode === "coding" ? "Coding" : "Chat";
        meta.appendChild(modeTag);

        const titleWrap = document.createElement("div");
        titleWrap.className = "conv-title-wrap";
        titleWrap.append(title, meta);

        const deleteButton = document.createElement("button");
        deleteButton.className = "conv-delete";
        deleteButton.type = "button";
        deleteButton.innerHTML = '<i class="fas fa-trash"></i>';
        deleteButton.addEventListener("click", async (event) => {
            event.stopPropagation();
            await apiFetch(`/api/conversations/${conversation.id}`, { method: "DELETE" });
            if (state.currentConvId === conversation.id) {
                startNewChat();
            }
            await loadConversations();
        });

        const actions = document.createElement("div");
        actions.className = "conv-actions";
        actions.append(deleteButton);

        item.append(titleWrap, actions);
        item.addEventListener("click", () => loadConversation(conversation.id, conversation));
        return item;
    }

    function renderMemoryItem(memory) {
        const item = document.createElement("button");
        item.className = "memory-item";
        item.type = "button";
        item.innerHTML = `
            <span class="memory-item-title">${memory.title}</span>
            <span class="memory-item-copy">${memory.content}</span>
        `;
        item.addEventListener("click", () => openMemoryModal(memory));
        return item;
    }

    async function loadConversations() {
        if (!state.user) {
            return;
        }
        const conversations = await apiFetch("/api/conversations");
        convList.innerHTML = "";
        conversations.forEach((conversation) => convList.appendChild(renderConversationItem(conversation)));
    }

    async function loadMemories() {
        if (!state.user) {
            return;
        }
        state.memories = await apiFetch("/api/memories");
        memoryHubBtn.innerHTML = `<i class="fas fa-brain"></i> Memories${state.memories.length ? ` (${state.memories.length})` : ""}`;
        memoryList.innerHTML = "";
        if (!state.memories.length) {
            memoryList.innerHTML = '<div class="empty-panel-copy">Nothing saved yet.</div>';
            return;
        }
        state.memories.forEach((memory) => memoryList.appendChild(renderMemoryItem(memory)));
    }

    async function loadConversation(id, conversationMeta = null) {
        if (conversationMeta) {
            state.currentMode = conversationMeta.mode || "companion";
            modeButtons.forEach((button) => {
                button.classList.toggle("active", button.dataset.mode === state.currentMode);
            });
            updateModeUI();
        }
        state.currentConvId = id;
        chatContainer.innerHTML = "";
        const messages = await apiFetch(`/api/conversations/${id}/messages`);
        if (!messages.length) {
            chatContainer.appendChild(createWelcome());
        } else {
            const lastAssistantIndex = [...messages].map((message) => message.role).lastIndexOf("assistant");
            messages.forEach((message, index) => addMessage(
                message.content,
                message.role,
                message.timestamp,
                null,
                null,
                index === lastAssistantIndex,
            ));
        }
        document.querySelectorAll(".conv-item").forEach((el) => {
            el.classList.toggle("active", Number(el.dataset.id) === id);
        });
        topbarTitle.textContent = document.querySelector(`.conv-item[data-id="${id}"] .conv-item-title`)?.textContent || topbarTitle.textContent;
        scrollToBottom();
        closeSidebar();
    }

    async function sendMessage(message, voiceData) {
        if (!message && !voiceData) {
            return;
        }
        if (message && message !== "Voice input") {
            addMessage(message, "user", new Date().toISOString(), null);
        }

        addTypingIndicator();
        const preference = getCurrentPreference();
        const payload = {
            model: modelSelect.value,
            mode: state.currentMode,
            persona_name: preference.persona_name,
            system_prompt: preference.system_prompt,
        };
        if (message) payload.message = message;
        if (voiceData) payload.voice_data = voiceData;
        if (state.currentConvId) payload.conversation_id = state.currentConvId;

        try {
            const data = await apiFetch("/api/chat", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            removeTypingIndicator();
            if (data.conversation_id) {
                state.currentConvId = data.conversation_id;
                topbarTitle.textContent = data.conversation_title;
                await loadConversations();
            }
            addMessage(data.message, "assistant", data.timestamp, data.audio || null, data.memory_suggestion || null, true);
            if (Array.isArray(data.web_fetch_errors) && data.web_fetch_errors.length) {
                const details = data.web_fetch_errors
                    .map((item) => `${item.url}: ${item.error}`)
                    .join("\n");
                addMessage(`I couldn't read part of the web content:\n${details}`, "assistant", new Date().toISOString(), null);
            }
            if (data.local_mode) {
                apiNoticeText.textContent = data.fallback_reason
                    ? `Fallback reason: ${data.fallback_reason}`
                    : "Running in fallback mode because no external model answered.";
                apiNotice.classList.remove("hidden");
            } else {
                apiNotice.classList.add("hidden");
                apiNoticeText.textContent = "Running in fallback mode because no external model answered.";
            }
            if (data.audio && state.enableVoiceOutput) {
                responseAudio.src = data.audio;
                responseAudio.play();
            }
        } catch (error) {
            removeTypingIndicator();
            addMessage(error.message || "Something went wrong. Please try again.", "assistant", new Date().toISOString(), null);
        }
    }

    function handleSend() {
        const text = userInput.value.trim();
        if (!text) return;
        userInput.value = "";
        userInput.style.height = "auto";
        sendMessage(text, null);
    }

    function stopRecordingFn() {
        if (state.mediaRecorder && state.isRecording) {
            state.mediaRecorder.stop();
        }
    }

    function startRecording() {
        if (state.isRecording || !state.enableVoiceInput) {
            return;
        }
        navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
            state.isRecording = true;
            recordingBar.classList.add("active");
            micButton.classList.add("recording");
            try {
                state.mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
            } catch (error) {
                state.mediaRecorder = new MediaRecorder(stream);
            }
            state.audioChunks = [];
            state.mediaRecorder.addEventListener("dataavailable", (event) => {
                if (event.data.size > 0) {
                    state.audioChunks.push(event.data);
                }
            });
            state.mediaRecorder.addEventListener("stop", () => {
                const blob = new Blob(state.audioChunks, { type: state.mediaRecorder.mimeType || "audio/webm" });
                const reader = new FileReader();
                reader.onloadend = () => sendMessage("Voice input", reader.result);
                reader.readAsDataURL(blob);
                stream.getTracks().forEach((track) => track.stop());
                state.isRecording = false;
                recordingBar.classList.remove("active");
                micButton.classList.remove("recording");
            });
            state.mediaRecorder.start(100);
            setTimeout(() => {
                if (state.isRecording) stopRecordingFn();
            }, 5000);
        }).catch(() => {
            state.isRecording = false;
        });
    }

    async function bootstrap() {
        const data = await fetch("/api/bootstrap").then((response) => response.json());
        state.csrfToken = data.csrf_token || "";
        state.user = data.user;
        state.preferences = data.preferences || {};
        state.memories = data.memories || [];
        updateAuthenticatedUI();
        if (state.user) {
            await loadConversations();
            await loadMemories();
            modelSelect.value = "gpt-4.1-mini";
            startNewChat();
            userInput.focus();
        }
    }

    async function handleAuthSubmit(event) {
        event.preventDefault();
        authError.textContent = "";
        try {
            const data = await apiFetch(`/api/auth/${authMode}`, {
                method: "POST",
                body: JSON.stringify({
                    email: authEmail.value.trim(),
                    password: authPassword.value,
                }),
            });
            state.user = data.user;
            state.csrfToken = data.csrf_token || state.csrfToken;
            state.preferences = {};
            authForm.reset();
            updateAuthenticatedUI();
            await loadConversations();
            await loadMemories();
            startNewChat();
        } catch (error) {
            authError.textContent = error.message;
        }
    }

    async function handleLogout() {
        const data = await apiFetch("/api/auth/logout", { method: "POST" });
        state.user = null;
        state.csrfToken = data.csrf_token || state.csrfToken;
        state.currentConvId = null;
        state.preferences = {};
        state.memories = [];
        convList.innerHTML = "";
        memoryList.innerHTML = "";
        memoryHubBtn.innerHTML = '<i class="fas fa-brain"></i> Memories';
        chatContainer.innerHTML = "";
        chatContainer.appendChild(createWelcome());
        updateAuthenticatedUI();
    }

    function openProfileModal() {
        profileName.value = state.user?.display_name || "";
        profileAbout.value = state.user?.about_me || "";
        profileError.textContent = "";
        profileModal.classList.add("open");
    }

    function closeProfileModal() {
        profileModal.classList.remove("open");
    }

    async function saveProfile() {
        profileError.textContent = "";
        try {
            const user = await apiFetch("/api/profile", {
                method: "PATCH",
                body: JSON.stringify({
                    display_name: profileName.value.trim(),
                    about_me: profileAbout.value.trim(),
                }),
            });
            state.user = user;
            updateAuthenticatedUI();
            closeProfileModal();
        } catch (error) {
            profileError.textContent = error.message;
        }
    }

    function openSettings() {
        const preference = getCurrentPreference();
        personaNameEl.value = preference.persona_name || "";
        personaPromptEl.value = preference.system_prompt || "";
        voiceProviderEl.value = preference.voice_provider || "browser";
        voiceNameEl.value = preference.voice_name || "";
        presetButtons.forEach((button) => {
            button.classList.toggle(
                "selected",
                button.dataset.name === personaNameEl.value && button.dataset.prompt === personaPromptEl.value,
            );
        });
        settingsModal.classList.add("open");
    }

    function closeSettings() {
        settingsModal.classList.remove("open");
    }

    async function saveSettings() {
        const preference = await apiFetch(`/api/preferences/${state.currentMode}`, {
            method: "PUT",
            body: JSON.stringify({
                persona_name: personaNameEl.value.trim(),
                system_prompt: personaPromptEl.value.trim(),
                voice_provider: voiceProviderEl.value,
                voice_name: voiceNameEl.value.trim(),
            }),
        });
        state.preferences[state.currentMode] = preference;
        applyPersona();
        startNewChat();
        closeSettings();
    }

    async function resetSettings() {
        await apiFetch(`/api/preferences/${state.currentMode}`, { method: "DELETE" });
        delete state.preferences[state.currentMode];
        applyPersona();
        startNewChat();
        closeSettings();
    }

    function openMemoryModal(memory = null) {
        state.editingMemoryId = memory ? memory.id : null;
        memoryTitle.value = memory?.title || "";
        memoryContent.value = memory?.content || "";
        memoryError.textContent = "";
        memoryDelete.classList.toggle("hidden", !memory);
        memoryModal.classList.add("open");
    }

    function closeMemoryModal() {
        memoryModal.classList.remove("open");
        state.editingMemoryId = null;
    }

    function openMemoryHub() {
        memoryHubModal.classList.add("open");
    }

    function closeMemoryHub() {
        memoryHubModal.classList.remove("open");
    }

    function openQuickControls() {
        quickControlsModal.classList.add("open");
        closeSidebar();
    }

    function closeQuickControls() {
        quickControlsModal.classList.remove("open");
    }


    async function saveMemory() {
        memoryError.textContent = "";
        const payload = {
            title: memoryTitle.value.trim(),
            content: memoryContent.value.trim(),
        };
        if (!payload.title || !payload.content) {
            memoryError.textContent = "Title and content are required.";
            return;
        }
        if (state.editingMemoryId) {
            await apiFetch(`/api/memories/${state.editingMemoryId}`, {
                method: "PATCH",
                body: JSON.stringify(payload),
            });
        } else {
            await apiFetch("/api/memories", {
                method: "POST",
                body: JSON.stringify(payload),
            });
        }
        await loadMemories();
        closeMemoryModal();
    }

    async function removeMemory() {
        if (!state.editingMemoryId) return;
        await apiFetch(`/api/memories/${state.editingMemoryId}`, { method: "DELETE" });
        await loadMemories();
        closeMemoryModal();
    }

    function openImportModal() {
        importFile.value = "";
        importError.textContent = "";
        importModal.classList.add("open");
    }

    function closeImportModal() {
        importModal.classList.remove("open");
    }

    async function runImport() {
        importError.textContent = "";
        const file = importFile.files?.[0];
        if (!file) {
            importError.textContent = "Choose the ChatGPT export zip or conversations.json first.";
            return;
        }
        const formData = new FormData();
        formData.append("file", file);
        try {
            await apiFetch("/api/import/chatgpt", {
                method: "POST",
                body: formData,
            });
            await loadConversations();
            closeImportModal();
        } catch (error) {
            importError.textContent = error.message;
        }
    }

    authTabs.forEach((tab) => tab.addEventListener("click", () => updateAuthMode(tab.dataset.authMode)));
    authForm.addEventListener("submit", handleAuthSubmit);
    profileBtn.addEventListener("click", openProfileModal);
    logoutBtn.addEventListener("click", handleLogout);

    sidebarToggle.addEventListener("click", openSidebar);
    sidebarOverlay.addEventListener("click", closeSidebar);
    newChatBtn.addEventListener("click", startNewChat);
    newChatBtnMobile.addEventListener("click", startNewChat);
    newMemoryBtn.addEventListener("click", () => openMemoryModal());
    memoryHubBtn.addEventListener("click", openMemoryHub);
    quickControlsBtn.addEventListener("click", openQuickControls);
    quickControlsBtnMobile.addEventListener("click", openQuickControls);

    userInput.addEventListener("input", function onInput() {
        this.style.height = "auto";
        this.style.height = `${Math.min(this.scrollHeight, 220)}px`;
    });
    userInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
        }
    });
    sendBtn.addEventListener("click", handleSend);

    voiceToggle.addEventListener("click", function toggleVoiceInput() {
        state.enableVoiceInput = !state.enableVoiceInput;
        this.classList.toggle("active", state.enableVoiceInput);
    });
    audioToggle.addEventListener("click", function toggleVoiceOutput() {
        if (state.currentMode === "coding") return;
        state.enableVoiceOutput = !state.enableVoiceOutput;
        this.classList.toggle("active", state.enableVoiceOutput);
    });
    micButton.addEventListener("click", () => (state.isRecording ? stopRecordingFn() : startRecording()));
    stopRecording.addEventListener("click", stopRecordingFn);

    modeButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            state.currentMode = button.dataset.mode;
            modeButtons.forEach((item) => item.classList.toggle("active", item === button));
            updateModeUI();
            await loadConversations();
            startNewChat();
        });
    });

    settingsBtn.addEventListener("click", openSettings);
    settingsClose.addEventListener("click", closeSettings);
    settingsModal.addEventListener("click", (event) => {
        if (event.target === settingsModal) closeSettings();
    });
    settingsSave.addEventListener("click", saveSettings);
    settingsReset.addEventListener("click", resetSettings);
    presetButtons.forEach((button) => {
        button.addEventListener("click", () => {
            personaNameEl.value = button.dataset.name;
            personaPromptEl.value = button.dataset.prompt;
            presetButtons.forEach((item) => item.classList.toggle("selected", item === button));
        });
    });

    profileClose.addEventListener("click", closeProfileModal);
    profileModal.addEventListener("click", (event) => {
        if (event.target === profileModal) closeProfileModal();
    });
    profileSave.addEventListener("click", saveProfile);

    memoryClose.addEventListener("click", closeMemoryModal);
    memoryModal.addEventListener("click", (event) => {
        if (event.target === memoryModal) closeMemoryModal();
    });
    memorySave.addEventListener("click", saveMemory);
    memoryDelete.addEventListener("click", removeMemory);
    memoryHubClose.addEventListener("click", closeMemoryHub);
    memoryHubModal.addEventListener("click", (event) => {
        if (event.target === memoryHubModal) closeMemoryHub();
    });
    quickControlsClose.addEventListener("click", closeQuickControls);
    quickControlsModal.addEventListener("click", (event) => {
        if (event.target === quickControlsModal) closeQuickControls();
    });

    importBtn.addEventListener("click", openImportModal);
    importClose.addEventListener("click", closeImportModal);
    importCancel.addEventListener("click", closeImportModal);
    importModal.addEventListener("click", (event) => {
        if (event.target === importModal) closeImportModal();
    });
    importStart.addEventListener("click", runImport);

    updateAuthMode("login");
    bootstrap().catch((error) => {
        authError.textContent = error.message;
    });
});
