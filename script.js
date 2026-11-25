
const projectorList = document.getElementById("projectorList");
const projectorForm = document.getElementById("projectorForm");
const formMessage = document.getElementById("formMessage");

const loginPanel = document.getElementById("loginPanel");
const dashboard = document.getElementById("dashboard");
const loginForm = document.getElementById("loginForm");
const loginPassword = document.getElementById("loginPassword");
const loginMessage = document.getElementById("loginMessage");
const logoutBtn = document.getElementById("logoutBtn");

let csrfToken = "";

async function apiRequest(url, method = "GET", data = undefined) {
    const options = {
        method,
        credentials: "same-origin",
        headers: {}
    };

    if (method !== "GET") {
        options.headers["X-CSRF-Token"] = csrfToken;
    }

    if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }

    const response = await fetch(url, options);

    let result;
    try {
        result = await response.json();
    } catch {
        throw new Error("The server returned an invalid response.");
    }

    if (response.status === 401 && url !== "/api/login") {
        showLogin("Your session has ended. Please log in again.");
        throw new Error("Please log in again.");
    }

    if (!response.ok || result.success === false) {
        throw new Error(result.message || `Request failed (${response.status})`);
    }

    return result;
}

function showLogin(message = "") {
    dashboard.hidden = true;
    loginPanel.hidden = false;
    logoutBtn.hidden = true;
    loginPassword.value = "";
    loginMessage.textContent = message;
    loginPassword.focus();
}

function showDashboard() {
    loginPanel.hidden = true;
    dashboard.hidden = false;
    logoutBtn.hidden = false;
    loginMessage.textContent = "";
}

async function checkAuthentication() {
    try {
        const response = await fetch("/api/auth/status", {
            credentials: "same-origin"
        });

        const result = await response.json();
        csrfToken = result.csrf_token || "";

        if (result.authenticated) {
            showDashboard();
            await loadProjectors();
        } else {
            showLogin();
        }
    } catch {
        showLogin("Unable to contact the server. Refresh the page.");
    }
}

loginForm.addEventListener("submit", async event => {
    event.preventDefault();
    loginMessage.textContent = "Checking password…";

    try {
        const result = await apiRequest("/api/login", "POST", {
            password: loginPassword.value
        });

        csrfToken = result.csrf_token;
        showDashboard();
        await loadProjectors();
    } catch (error) {
        loginMessage.textContent = error.message;
    }
});

logoutBtn.addEventListener("click", async () => {
    try {
        await apiRequest("/api/logout", "POST", {});
        showLogin("You have been logged out.");
    } catch (error) {
        showMessage(formMessage, error.message, "error");
    }
});

function makeButton(text, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.className = className;
    button.addEventListener("click", handler);
    return button;
}

function showMessage(element, message, kind = "") {
    element.textContent = message;
    element.className = `message ${kind}`.trim();
}

async function loadProjectors() {
    try {
        const devices = await apiRequest("/api/projectors");
        projectorList.replaceChildren();

        if (!devices.length) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.textContent = "No projector profiles yet. Add an authorized projector above.";
            projectorList.appendChild(empty);
            return;
        }

        devices.forEach(device => {
            const card = document.createElement("article");
            card.className = "device-card";

            const top = document.createElement("div");
            top.className = "device-top";

            const headingWrap = document.createElement("div");
            const heading = document.createElement("h3");
            heading.textContent = device.name;

            const meta = document.createElement("div");
            meta.className = "device-meta";
            meta.textContent = `${device.brand} ${device.model} · ${device.ip} · ${device.protocol}`;

            headingWrap.append(heading, meta);

            const badge = document.createElement("span");
            badge.className = "state-pill";
            if (device.connection === "CONNECTED") badge.classList.add("connected");
            if (device.connection === "FAILED") badge.classList.add("failed");
            badge.textContent = device.connection;

            top.append(headingWrap, badge);

            const status = document.createElement("p");
            status.className = "device-status";
            status.innerHTML = "Verified power state: <strong></strong>";
            status.querySelector("strong").textContent = device.power;

            const actions = document.createElement("div");
            actions.className = "device-actions";

            actions.append(
                makeButton("TEST CONNECTION", "connect-btn", () => connectDevice(device.id)),
                makeButton("POWER ON", "on-btn", () => sendPower(device.id, "ON")),
                makeButton("POWER OFF", "off-btn", () => sendPower(device.id, "OFF")),
                makeButton("DELETE", "delete-btn", () => deleteDevice(device.id))
            );

            card.append(top, status, actions);
            projectorList.appendChild(card);
        });
    } catch (error) {
        if (!error.message.includes("log in")) {
            projectorList.textContent = `Unable to load devices: ${error.message}`;
        }
    }
}

projectorForm.addEventListener("submit", async event => {
    event.preventDefault();
    showMessage(formMessage, "Saving projector profile…");

    const data = {
        name: document.getElementById("name").value.trim(),
        brand: document.getElementById("brand").value,
        model: document.getElementById("model").value.trim(),
        ip: document.getElementById("ip").value.trim(),
        password: document.getElementById("password").value
    };

    try {
        const result = await apiRequest("/api/projectors", "POST", data);
        projectorForm.reset();
        showMessage(formMessage, result.message, "success");
        await loadProjectors();
    } catch (error) {
        showMessage(formMessage, error.message, "error");
    }
});

async function connectDevice(id) {
    try {
        const result = await apiRequest(`/api/projectors/${id}/connect`, "POST", {});
        showMessage(formMessage, result.message, "success");
        await loadProjectors();
    } catch (error) {
        showMessage(formMessage, error.message, "error");
        await loadProjectors();
    }
}

async function sendPower(id, action) {
    if (!confirm(`Send REAL POWER ${action} command to this projector?`)) return;

    try {
        const result = await apiRequest(
            `/api/projectors/${id}/power`, "POST", { action }
        );
        showMessage(formMessage, result.message, "success");
        await loadProjectors();
    } catch (error) {
        showMessage(formMessage, error.message, "error");
        await loadProjectors();
    }
}

async function deleteDevice(id) {
    if (!confirm("Delete this projector profile and clear its in-memory credentials?")) return;

    try {
        const result = await apiRequest(`/api/projectors/${id}`, "DELETE");
        showMessage(formMessage, result.message, "success");
        await loadProjectors();
    } catch (error) {
        showMessage(formMessage, error.message, "error");
    }
}

document.getElementById("refreshBtn").addEventListener("click", loadProjectors);

checkAuthentication();
