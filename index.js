const sendBtn = document.getElementById("send-btn") // pressing the send button
const userInput = document.getElementById("user-input") // the user's message, as it would appear in the chat window
const chatWindow = document.getElementById("chat-window") // chat window, self explanatory
const mediaUpload = document.getElementById("media-upload") // the button to upload images/videos

sendBtn.addEventListener("click", function () {
    const wrapper = document.createElement("div")
    wrapper.style.textAlign = "right" // user's messages go right, bot responses - left

    const message = userInput.value

    if (message.trim() === "") return // if text box is blank, do not do anything

    const userDiv = document.createElement("div")
    userDiv.innerText = message
    userDiv.classList.add("user-message")

    const loadingDiv = document.createElement("div") // a loading indicator consiting of triple dots
    loadingDiv.innerText = ". . ."
    loadingDiv.id = "loading"

    wrapper.appendChild(userDiv) // groups the user's messager
    chatWindow.appendChild(wrapper) // adds user's message to chat
    chatWindow.appendChild(loadingDiv) // shows loading indicator while bot thinks

    userInput.value = "" // after submitting, clears the text box

    fetch("http://localhost:8000/chat", { // this is how it is sent to the backend via FastAPI
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: message })
    })
        .then(function (response) {
            const reader = response.body.getReader() // extracts chunks from backend response
            const decoder = new TextDecoder() // streaming gives raw bytes, this converts it to a readable string
            const div = document.createElement("div") // this is the division to which the stream chunks get added for the bot response
            div.classList.add("bot-message")
            document.getElementById("loading").remove()
            chatWindow.appendChild(div) // div gets added to chat

            let isStatus = true

            function read() {
                reader.read().then(function ({ done, value }) {
                    if (done) return // once streaming has ended, stops the function
                    const token = decoder.decode(value)
                    if (token === "Thinking..." || token === "Reviewing...") {
                        div.innerText = token
                        div.classList.add("pulsing")
                    } else {
                        if (isStatus) {
                            div.innerText = ""
                            div.classList.remove("pulsing")
                            isStatus = false // once the real response comes, the loading indicators get removed and the response starts streaming below
                        }
                        div.innerText += token
                    }
                    read()
                })
            }
            read()
        })


})


userInput.addEventListener("keydown", function (event) { // allows pressing "enter" instead of clicking button
    if (event.key === "Enter") {
        sendBtn.click()
    }
})

mediaUpload.addEventListener("change", function () { // sends uploads to backend
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