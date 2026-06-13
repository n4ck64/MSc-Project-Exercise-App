const sendBtn = document.getElementById("send-btn") // pressing the send button
const userInput = document.getElementById("user-input") // the user's message, as it would appear in the chat window
const chatWindow = document.getElementById("chat-window") // chat window, self explanatory
const mediaUpload = document.getElementById("media-upload") // the button to upload images/videos
let pendingImage = null
let pendingVideoChoice = null
let pendingFileType = null

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

    if (pendingImage) {
        const imgWrapper = document.createElement("div")
        imgWrapper.style.textAlign = "right"
        if (pendingFileType === "video") {
            const vid = document.createElement("video")
            vid.src = document.getElementById("video-preview").src // what actually appears on the browser
            vid.style.maxWidth = "200px"
            vid.controls = true
            imgWrapper.appendChild(vid)
            document.getElementById("video-preview").style.display = "none"
        } else {
            const img = document.createElement("img")
            img.src = document.getElementById("image-preview").src
            img.style.maxWidth = "200px"
            img.style.borderRadius = "10px"
            imgWrapper.appendChild(img)
            document.getElementById("image-preview").style.display = "none"
        }
        chatWindow.appendChild(imgWrapper)
    }
    wrapper.appendChild(userDiv) // groups the user's messager
    chatWindow.appendChild(wrapper) // adds user's message to chat
    chatWindow.appendChild(loadingDiv) // shows loading indicator while bot thinks

    userInput.value = "" // after submitting, clears the text box

    fetch("http://localhost:8000/chat", { // this is how it is sent to the backend via FastAPI
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: message, image_path: pendingImage, file_type: pendingFileType, video_choice: pendingVideoChoice })
    })
        .then(function (response) {
            pendingImage = null
            pendingFileType = null
            pendingVideoChoice = null
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
                    console.log(token)
                    if (token === "Thinking..." || token === "Reviewing..." || token === "Analysing..." || token == "Processing...") {
                        div.innerText = token
                        div.classList.add("pulsing")
                    } else if (token.startsWith("CHOICES:")) {
                        div.innerText = ""
                        const names = token.replace("CHOICES:", "").split(",")
                        names.forEach(function (name) {
                            const button = document.createElement("button")
                            button.classList.add("choice-btn")
                            button.innerText = name
                            chatWindow.appendChild(button)
                            button.addEventListener("click", function () {
                                pendingVideoChoice = name
                                userInput.value = name
                                sendBtn.click()
                                document.querySelectorAll(".choice-btn").forEach(b => b.remove())
                            })
                        })
                        const noneBtn = document.createElement("button")
                        noneBtn.innerText = "None of the above"
                        noneBtn.classList.add("choice-btn")
                        noneBtn.addEventListener("click", function () {
                            pendingVideoChoice = "manual"
                            sendBtn.click()
                            document.querySelectorAll(".choice-btn").forEach(b => b.remove())
                        })
                        chatWindow.appendChild(noneBtn)
                    }
                    else {
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


userInput.addEventListener("keydown", function (event) { // allows pressing "Enter" instead of clicking button
    if (event.key === "Enter") {
        sendBtn.click()
    }
})

mediaUpload.addEventListener("change", function () { // sends uploads to backend
    const file = mediaUpload.files[0] // files is a list of selected files, [0] grabs the first and only one

    const formData = new FormData() // FormData is an object for sending files over HTTP, which unlike JSPN can handle binary data like images and videos
    formData.append("file", file) // must match parameter in upload_endpoint for FastAPI

    const reader = new FileReader() // uploads the image in the chat window
    reader.onload = function (e) {
        if (file.type.startsWith("video")) {
            const preview = document.getElementById("video-preview")
            preview.src = e.target.result
            preview.style.display = "block"
        } else {
            const preview = document.getElementById("image-preview")
            preview.src = e.target.result
            preview.style.display = "block"
        }
        const loadingDiv = document.createElement("div") // loading indicator shown while backend processes media
        loadingDiv.innerText = "Uploading..."
        loadingDiv.id = "loading"
        chatWindow.appendChild(loadingDiv)
    }

    reader.readAsDataURL(file) // reads the image and converts it to a URL, once it is loaded, it gets fired on the reader.onload function



    fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData
    })
        .then(function (response) {
            return response.json()
        })
        .then(function (data) {
            document.getElementById("loading").remove()
            pendingImage = data.file_path
            pendingFileType = file.type.startsWith("video") ? "video" : "image"
        })

})