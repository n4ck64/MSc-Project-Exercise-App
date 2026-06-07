const sendBtn = document.getElementById("send-btn")
const userInput = document.getElementById("user-input")
const chatWindow = document.getElementById("chat-window")

sendBtn.addEventListener("click", function () {
    const message = userInput.value
    chatWindow.innerText += message + "\n"
    userInput.value = ""
})