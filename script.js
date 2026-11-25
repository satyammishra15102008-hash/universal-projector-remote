const projectorList = document.getElementById("projectorList");
const projectorForm = document.getElementById("projectorForm");
const formMessage = document.getElementById("formMessage");

async function apiRequest(url, method = "GET", data = undefined) {
    const options = { method, headers: {} };
    if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || result.success === false) {
        throw new Error(result.message || `Request failed (${response.status})`);
    }
    return result;
}

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
        projectorList.textContent = `Unable to load devices: ${error.message}`;
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
    const confirmed = confirm(`Send REAL POWER ${action} command to this projector?`);
    if (!confirmed) return;

    try {
        const result = await apiRequest(`/api/projectors/${id}/power`, "POST", { action });
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
loadProjectors();
