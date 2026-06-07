const sendBtn = document.getElementById("send-btn")
const userInput = document.getElementById("user-input")
const chatWindow = document.getElementById("chat-window")

sendBtn.addEventListener("click", function () {
    const wrapper = document.createElement("div")
    wrapper.style.textAlign = "right"

    const message = userInput.value

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
