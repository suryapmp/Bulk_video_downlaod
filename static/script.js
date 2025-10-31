const form = document.getElementById("uploadForm");
const tableBody = document.querySelector("#logTable tbody");

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = document.getElementById("fileInput").files[0];
    if (!file) return alert("Please choose an Excel file.");

    const fd = new FormData();
    fd.append("file", file);

    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();

    if (data.error) alert(data.error);
    else alert(data.message);
});

const ws = new WebSocket(`ws://${window.location.host}/ws`);

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const { roll_no, program, course, status, progress, speed } = msg;

    let row = document.getElementById(roll_no);
    if (!row) {
        row = document.createElement("tr");
        row.id = roll_no;
        row.innerHTML = `
            <td>${roll_no}</td>
            <td>${program}</td>
            <td>${course}</td>
            <td class="status">${status}</td>
            <td>
                <div class="progress"><div class="bar" style="width:${progress}%"></div></div>
            </td>
            <td class="speed">${speed}</td>
        `;
        tableBody.appendChild(row);
    } else {
        row.querySelector(".status").textContent = status;
        row.querySelector(".bar").style.width = `${progress}%`;
        row.querySelector(".speed").textContent = speed;
    }
};
