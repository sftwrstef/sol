document.addEventListener("DOMContentLoaded", () => {
    const state = {
        csrfToken: "",
        user: null,
        currentConvId: null,
        currentMode: "companion",
        enableVoiceInput: true,
        enableVoiceOutput: false,
        enableEmotion: true,
        isRecording: false,
        mediaRecorder: null,
        audioChunks: [],
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
    const accountEmail = document.getElementById("accountEmail");
    const logoutBtn = document.getElementById("logoutBtn");

    const chatContainer = document.getElementById("chatContainer");
    const convList = document.getElementById("convList");
    const newChatBtn = document.getElementById("newChatBtn");
    const newChatBtnMobile = document.getElementById("newChatBtnMobile");
    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const topbarTitle = document.getElementById("topbarTitle");
    const welcomeHeading = document.getElementById("welcomeHeading");
    const welcomeSub = document.getElementById("welcomeSub");

    const modeButtons = document.querySelectorAll(".mode-btn");
    const modeBadge = document.getElementById("modeBadge");
    const composerTip = document.getElementById("composerTip");
    const modelSelect = document.getElementById("modelSelect");
    const userInput = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    const micButton = document.getElementById("micButton");
    const stopRecording = document.getElementById("stopRecording");
    const recordingBar = document.getElementById("recordingBar");
    const responseAudio = document.getElementById("responseAudio");
    const apiNotice = document.getElementById("apiNotice");
    const voiceToggle = document.getElementById("voiceToggle");
    const audioToggle = document.getElementById("audioToggle");
    const emotionToggle = document.getElementById("emotionToggle");

    const settingsBtn = document.getElementById("settingsBtn");
    const settingsModal = document.getElementById("settingsModal");
    const settingsClose = document.getElementById("settingsClose");
    const settingsSave = document.getElementById("settingsSave");
    const settingsReset = document.getElementById("settingsReset");
    const personaNameEl = document.getElementById("personaName");
    const personaPromptEl = document.getElementById("personaPrompt");
    const presetButtons = document.querySelectorAll(".preset-btn");

    let authMode = "login";

    function openSidebar() {
        sidebar.classList.add("open");
        sidebarOverlay.classList.add("open");
    }

    function closeSidebar() {
        sidebar.classList.remove("open");
        sidebarOverlay.classList.remove("open");
    }

    function updateAuthMode(nextMode) {
        authMode = nextMode;
        authTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.authMode === nextMode));
        authSubmit.textContent = nextMode === "login" ? "Log in" : "Create account";
        authHint.textContent = nextMode === "login"
            ? "Use your account to access your private conversations."
            : "Passwords must be at least 8 characters.";
        authError.textContent = "";
        authPassword.autocomplete = nextMode === "login" ? "current-password" : "new-password";
    }

    function getPersonaStorageKey(suffix) {
        return `sol_${state.currentMode}_${suffix}`;
    }

    function loadPersona() {
        return {
            name: localStorage.getItem(getPersonaStorageKey("persona_name")) || "",
            prompt: localStorage.getItem(getPersonaStorageKey("persona_prompt")) || "",
        };
    }

    function savePersona(name, prompt) {
        localStorage.setItem(getPersonaStorageKey("persona_name"), name);
        localStorage.setItem(getPersonaStorageKey("persona_prompt"), prompt);
    }

    function applyPersona() {
        const persona = loadPersona();
        const label = persona.name || (state.currentMode === "coding" ? "Sol Code" : "Sol");
        document.querySelectorAll(".msg-row.assistant .msg-avatar").forEach((el) => { el.textContent = label; });
        document.querySelectorAll(".msg-row.assistant .msg-name").forEach((el) => { el.textContent = label; });
        const logo = document.querySelector(".welcome-logo");
        if (logo) {
            logo.textContent = label.slice(0, 3);
        }
    }

    async function apiFetch(url, options = {}) {
        const opts = { ...options };
        opts.headers = { ...(opts.headers || {}) };
        if (opts.body && !opts.headers["Content-Type"]) {
            opts.headers["Content-Type"] = "application/json";
        }
        if (["POST", "PATCH", "PUT", "DELETE"].includes((opts.method || "GET").toUpperCase())) {
            opts.headers["X-CSRF-Token"] = state.csrfToken;
        }

        const response = await fetch(url, opts);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || "Request failed");
        }
        return data;
    }

    function createWelcome() {
        const el = document.createElement("div");
        el.className = "welcome-block";
        el.id = "welcomeBlock";

        const logo = document.createElement("div");
        logo.className = "welcome-logo";
        logo.textContent = state.currentMode === "coding" ? "Cod" : "Sol";

        const heading = document.createElement("h2");
        heading.className = "welcome-heading";
        heading.textContent = state.currentMode === "coding" ? "What are we building?" : "How can I help you today?";

        const sub = document.createElement("p");
        sub.className = "welcome-sub";
        sub.textContent = state.currentMode === "coding"
            ? "Debug, review architecture, draft code, and plan production launches."
            : "A safe space to think, feel, and talk things through.";

        el.appendChild(logo);
        el.appendChild(heading);
        el.appendChild(sub);
        return el;
    }

    function resetComposerForMode() {
        const isCoding = state.currentMode === "coding";
        modeBadge.textContent = isCoding ? "Coding Mode" : "Companion Mode";
        composerTip.textContent = isCoding
            ? "Focused on debugging, architecture, implementation, and code review."
            : "Private emotional support and general chat.";
        welcomeHeading.textContent = isCoding ? "What are we building?" : "How can I help you today?";
        welcomeSub.textContent = isCoding
            ? "Debug, review architecture, draft code, and plan production launches."
            : "A safe space to think, feel, and talk things through.";
        userInput.placeholder = isCoding ? "Paste code or ask a coding question..." : "Message Sol...";
        audioToggle.disabled = isCoding;
        audioToggle.classList.toggle("disabled", isCoding);
        if (isCoding) {
            state.enableVoiceOutput = false;
            audioToggle.classList.remove("active");
        }
        applyPersona();
    }

    function updateAuthenticatedUI() {
        if (state.user) {
            accountEmail.textContent = state.user.email;
            authShell.classList.add("hidden");
            appShell.classList.remove("hidden");
            resetComposerForMode();
        } else {
            accountEmail.textContent = "";
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

    function addMessage(content, role, timestamp, emotion, audioData) {
        const welcome = document.getElementById("welcomeBlock");
        if (welcome) {
            welcome.remove();
        }

        const row = document.createElement("div");
        row.className = `msg-row ${role}`;

        const inner = document.createElement("div");
        inner.className = "msg-inner";

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.textContent = role === "user" ? "You" : (loadPersona().name || (state.currentMode === "coding" ? "Sol Code" : "Sol"));

        const wrap = document.createElement("div");
        wrap.className = "msg-content-wrap";

        const name = document.createElement("div");
        name.className = "msg-name";
        name.textContent = avatar.textContent;

        const body = document.createElement("div");
        body.className = "msg-content";

        if (emotion && state.enableEmotion && role === "user") {
            const icons = { happy: "😊", sad: "😢", angry: "😠", fearful: "😨", surprised: "😲" };
            if (icons[emotion]) {
                const badge = document.createElement("span");
                badge.className = "emotion-badge";
                badge.textContent = icons[emotion];
                body.appendChild(badge);
            }
        }

        const contentSpan = document.createElement("span");
        contentSpan.innerHTML = formatContent(content);
        body.appendChild(contentSpan);

        const timeEl = document.createElement("div");
        timeEl.className = "msg-time";
        if (timestamp) {
            timeEl.textContent = new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }

        wrap.appendChild(name);
        wrap.appendChild(body);
        wrap.appendChild(timeEl);

        if (audioData && role === "assistant") {
            const actions = document.createElement("div");
            actions.className = "msg-actions";
            const playBtn = document.createElement("button");
            playBtn.className = "audio-btn";
            playBtn.type = "button";
            playBtn.innerHTML = '<i class="fas fa-volume-up"></i> Play';
            playBtn.addEventListener("click", () => {
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
        const row = document.createElement("div");
        row.className = "typing-row";
        row.id = "typingIndicator";
        row.innerHTML = `
            <div class="typing-inner">
                <div class="msg-avatar assistant">${state.currentMode === "coding" ? "Sol Code" : "Sol"}</div>
                <div class="typing-dots"><span></span><span></span><span></span></div>
            </div>
        `;
        chatContainer.appendChild(row);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById("typingIndicator");
        if (indicator) {
            indicator.remove();
        }
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
        if (conversation.id === state.currentConvId) {
            item.classList.add("active");
        }

        const title = document.createElement("span");
        title.className = "conv-item-title";
        title.textContent = conversation.title;

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
            loadConversations();
        });

        item.appendChild(title);
        item.appendChild(deleteButton);
        item.addEventListener("click", () => loadConversation(conversation.id));
        return item;
    }

    async function loadConversations() {
        if (!state.user) {
            return;
        }

        try {
            const conversations = await apiFetch(`/api/conversations?mode=${state.currentMode}`);
            convList.innerHTML = "";
            conversations.forEach((conversation) => {
                convList.appendChild(renderConversationItem(conversation));
            });
        } catch (error) {
            console.error(error);
        }
    }

    async function loadConversation(id) {
        state.currentConvId = id;
        chatContainer.innerHTML = "";

        try {
            const messages = await apiFetch(`/api/conversations/${id}/messages`);
            if (!messages.length) {
                chatContainer.appendChild(createWelcome());
            } else {
                messages.forEach((message) => addMessage(message.content, message.role, message.timestamp, message.emotion, null));
            }
            document.querySelectorAll(".conv-item").forEach((el) => {
                el.classList.toggle("active", Number(el.dataset.id) === id);
            });
            const active = document.querySelector(`.conv-item[data-id="${id}"] .conv-item-title`);
            topbarTitle.textContent = active ? active.textContent : (state.currentMode === "coding" ? "Coding" : "Sol Space");
            scrollToBottom();
            closeSidebar();
        } catch (error) {
            console.error(error);
        }
    }

    async function sendMessage(message, voiceData) {
        if (!message && !voiceData) {
            return;
        }

        if (message && message !== "Voice input") {
            addMessage(message, "user", new Date().toISOString(), null, null);
        }

        addTypingIndicator();
        const persona = loadPersona();
        const payload = {
            model: modelSelect.value,
            mode: state.currentMode,
            persona_name: persona.name,
            system_prompt: persona.prompt,
        };
        if (message) {
            payload.message = message;
        }
        if (voiceData) {
            payload.voice_data = voiceData;
        }
        if (state.currentConvId) {
            payload.conversation_id = state.currentConvId;
        }

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

            if (data.emotion && state.enableEmotion) {
                const userRows = document.querySelectorAll(".msg-row.user");
                const lastUser = userRows[userRows.length - 1];
                const icons = { happy: "😊", sad: "😢", angry: "😠", fearful: "😨", surprised: "😲" };
                if (lastUser && icons[data.emotion]) {
                    const msgContent = lastUser.querySelector(".msg-content");
                    if (msgContent && !msgContent.querySelector(".emotion-badge")) {
                        const badge = document.createElement("span");
                        badge.className = "emotion-badge";
                        badge.textContent = icons[data.emotion];
                        msgContent.prepend(badge);
                    }
                }
            }

            addMessage(data.message, "assistant", data.timestamp, null, data.audio || null);
            apiNotice.classList.toggle("hidden", !data.local_mode);

            if (data.audio && state.enableVoiceOutput) {
                responseAudio.src = data.audio;
                responseAudio.play();
            }
        } catch (error) {
            removeTypingIndicator();
            addMessage(error.message || "Something went wrong. Please try again.", "assistant", new Date().toISOString(), null, null);
        }
    }

    function handleSend() {
        const text = userInput.value.trim();
        if (!text) {
            return;
        }
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
                if (state.isRecording) {
                    stopRecordingFn();
                }
            }, 5000);
        }).catch((error) => {
            console.error(error);
            state.isRecording = false;
        });
    }

    async function bootstrap() {
        try {
            const data = await fetch("/api/bootstrap").then((response) => response.json());
            state.csrfToken = data.csrf_token || "";
            state.user = data.user;
            updateAuthenticatedUI();
            if (state.user) {
                await loadConversations();
                startNewChat();
                userInput.focus();
            }
        } catch (error) {
            console.error(error);
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
            authForm.reset();
            updateAuthenticatedUI();
            startNewChat();
            loadConversations();
        } catch (error) {
            authError.textContent = error.message;
        }
    }

    async function handleLogout() {
        try {
            const data = await apiFetch("/api/auth/logout", { method: "POST" });
            state.user = null;
            state.csrfToken = data.csrf_token || state.csrfToken;
            state.currentConvId = null;
            convList.innerHTML = "";
            chatContainer.innerHTML = "";
            chatContainer.appendChild(createWelcome());
            updateAuthenticatedUI();
        } catch (error) {
            console.error(error);
        }
    }

    function openSettings() {
        const persona = loadPersona();
        personaNameEl.value = persona.name;
        personaPromptEl.value = persona.prompt;
        settingsModal.classList.add("open");
        presetButtons.forEach((button) => {
            button.classList.toggle("selected", button.dataset.prompt === persona.prompt && button.dataset.name === (persona.name || button.dataset.name));
        });
    }

    function closeSettings() {
        settingsModal.classList.remove("open");
    }

    authTabs.forEach((tab) => tab.addEventListener("click", () => updateAuthMode(tab.dataset.authMode)));
    authForm.addEventListener("submit", handleAuthSubmit);
    logoutBtn.addEventListener("click", handleLogout);

    sidebarToggle.addEventListener("click", openSidebar);
    sidebarOverlay.addEventListener("click", closeSidebar);
    newChatBtn.addEventListener("click", startNewChat);
    newChatBtnMobile.addEventListener("click", startNewChat);

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
        if (state.currentMode === "coding") {
            return;
        }
        state.enableVoiceOutput = !state.enableVoiceOutput;
        this.classList.toggle("active", state.enableVoiceOutput);
    });
    emotionToggle.addEventListener("click", function toggleEmotion() {
        state.enableEmotion = !state.enableEmotion;
        this.classList.toggle("active", state.enableEmotion);
        document.querySelectorAll(".emotion-badge").forEach((badge) => {
            badge.style.display = state.enableEmotion ? "inline-flex" : "none";
        });
    });

    micButton.addEventListener("click", () => (state.isRecording ? stopRecordingFn() : startRecording()));
    stopRecording.addEventListener("click", stopRecordingFn);

    modeButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            state.currentMode = button.dataset.mode;
            modeButtons.forEach((item) => item.classList.toggle("active", item === button));
            startNewChat();
            resetComposerForMode();
            await loadConversations();
        });
    });

    settingsBtn.addEventListener("click", openSettings);
    settingsClose.addEventListener("click", closeSettings);
    settingsModal.addEventListener("click", (event) => {
        if (event.target === settingsModal) {
            closeSettings();
        }
    });
    settingsSave.addEventListener("click", () => {
        savePersona(personaNameEl.value.trim(), personaPromptEl.value.trim());
        applyPersona();
        closeSettings();
    });
    settingsReset.addEventListener("click", () => {
        personaNameEl.value = "";
        personaPromptEl.value = "";
    });
    presetButtons.forEach((button) => {
        button.addEventListener("click", () => {
            personaNameEl.value = button.dataset.name;
            personaPromptEl.value = button.dataset.prompt;
            presetButtons.forEach((item) => item.classList.toggle("selected", item === button));
        });
    });

    updateAuthMode("login");
    bootstrap();
});
