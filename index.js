const sendBtn = document.getElementById("send-btn")
const userInput = document.getElementById("user-input")
const chatWindow = document.getElementById("chat-window")
const mediaUpload = document.getElementById("media-upload")

sendBtn.addEventListener("click", function () {
    const wrapper = document.createElement("div")
    wrapper.style.textAlign = "right"

    const message = userInput.value

    if (message.trim() === "") return

    const userDiv = document.createElement("div")
    userDiv.innerText = message
    userDiv.classList.add("user-message")

    const loadingDiv = document.createElement("div")
    loadingDiv.innerText = ". . ."
    loadingDiv.id = "loading"

    wrapper.appendChild(userDiv)
    chatWindow.appendChild(wrapper)
    chatWindow.appendChild(loadingDiv)

    userInput.value = ""

    fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: message })
    })
        .then(function (response) {
            return response.json()
        })
        .then(function (data) {
            document.getElementById("loading").remove()
            const div = document.createElement("div")
            div.innerText = data.response
            div.classList.add("bot-message")
            chatWindow.appendChild(div)

        })
})

userInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
        sendBtn.click()
    }
})

mediaUpload.addEventListener("change", function () {
    const file = mediaUpload.files[0]

    const formData = new FormData()
    formData.append("file", file)

    const loadingDiv = document.createElement("div")
    loadingDiv.innerText = ". . ."
    loadingDiv.id = "loading"

    chatWindow.appendChild(loadingDiv)

    fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData
    })
        .then(function (response) {
            return response.json()
        })
        .then(function (data) {
            console.log(data)
            document.getElementById("loading").remove()
            const div = document.createElement("div")
            div.innerText = data.response
            div.classList.add("bot-message")
            chatWindow.appendChild(div)
        })

})