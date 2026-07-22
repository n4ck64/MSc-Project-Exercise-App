import { useState, useEffect, useRef, type ChangeEvent } from 'react'
import ReactMarkdown from 'react-markdown'


type Message = {
    role: "user" | "bot"
    content: string
    pulsing?: boolean // ? means optional
    mediaUrl?: string
    mediaType?: "image" | "video"
}

type Choices = {
    message: string
    names: string[]
} | null

function Chat({ goToPlans }: { goToPlans: () => void }) {
    const [pendingImage, setPendingImage] = useState<string | null>(null)
    const [pendingVideoChoice, setPendingVideoChoice] = useState<string | null>(null)
    const [pendingFileType, setPendingFileType] = useState<"image" | "video" | null>(null)
    const [manualVideoEntry, setManualVideoEntry] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [choices, setChoices] = useState<Choices>(null)
    const [message, setMessage] = useState<string>("")
    const bottomRef = useRef<HTMLDivElement>(null)
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])   // runs every time messages changes

    const STATUS_TOKENS = new Set([
        "Thinking...", "Reviewing...", "Analysing...", "Processing...", "Hungry...", "Uploading..."
    ])


    function updateLastBot(content: string, pulsing: boolean) {
        setMessages(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: "bot", content, pulsing }
            return copy
        })
    }



    function handleChoice(name: string) {
        setChoices(null)
        if (name === "__manual__") {
            setManualVideoEntry(true)
            send("None of the above", "manual")
        } else {
            send(name, name)
        }
    }

    async function send(text: string, choice: string | null) {
        if (text.trim() === "") return

        // add the user's message, then an empty bot bubble we'll stream into
        setMessages(prev => [
            ...prev,
            { role: "user", content: text, mediaUrl: previewUrl ?? undefined, mediaType: pendingFileType ?? undefined },
            { role: "bot", content: "", pulsing: false },
        ])
        setMessage("")

        const res = await fetch("http://localhost:8000/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                content: text,
                image_path: pendingImage,
                file_type: pendingFileType,
                video_choice: choice,
            }),
        })

        setPendingImage(null)
        setPendingFileType(null)
        setPendingVideoChoice(null)
        setPreviewUrl(null)

        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let isStatus = true
        let botText = ""

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const token = decoder.decode(value)

            if (STATUS_TOKENS.has(token)) {
                updateLastBot(token, true)                 // show "Thinking..." pulsing
            } else if (token.startsWith("CHOICES:")) {
                const [msg, namesStr] = token.replace("CHOICES:", "").split("|")
                setChoices({ message: msg, names: namesStr.split(",") })
                updateLastBot("", false)
            } else {
                if (isStatus) { botText = ""; isStatus = false }  // first real token clears status
                botText += token
                updateLastBot(botText, false)
            }
        }
    }

    function handleSend() {
        let choice = pendingVideoChoice
        if (manualVideoEntry) {
            choice = message
            setManualVideoEntry(false)
        }
        send(message, choice)
    }

    async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0]
        if (!file) return

        const isVideo = file.type.startsWith("video")
        setPreviewUrl(URL.createObjectURL(file))
        setPendingFileType(isVideo ? "video" : "image")

        const formData = new FormData()
        formData.append("file", file)

        const res = await fetch("http://localhost:8000/upload", { method: "POST", body: formData })
        const data = await res.json()

        setPendingImage(data.file_path)
    }

    function ChoiceButtons({ choices, onPick }: { choices: Choices, onPick: (name: string) => void }) {
        return (
            <div className="bot-message" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div>{choices!.message}</div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                    {choices!.names.map(name => (
                        <button key={name} className="choice-btn" onClick={() => onPick(name)}>{name}</button>
                    ))}
                    <button className="choice-btn" onClick={() => onPick("__manual__")}>None of the above</button>
                </div>
            </div>
        )
    }

    return (
        <div id="chat-window">
            {messages.map((m, i) => (
                m.role === "user"
                    ? <div key={i} style={{ textAlign: "right" }}>
                        {m.mediaType === "video"
                            ? <video src={m.mediaUrl} controls style={{ maxWidth: "200px", display: "block", marginLeft: "auto" }} />
                            : m.mediaUrl && <img src={m.mediaUrl} style={{ maxWidth: "200px", borderRadius: "10px", display: "block", marginLeft: "auto" }} />
                        }
                        <div className="user-message">{m.content}
                        </div>
                    </div>
                    : <div key={i} className={m.pulsing ? "bot-message pulsing" : "bot-message"}>
                        <ReactMarkdown
                            components={{
                                // intercept our own "#plans" link: switch tabs in-app
                                // (and refresh Plans) instead of navigating the browser
                                a: ({ href, children }) =>
                                    href === "#plans"
                                        ? <a href="#plans" onClick={e => { e.preventDefault(); goToPlans() }}>{children}</a>
                                        : <a href={href}>{children}</a>
                            }}
                        >{m.content}</ReactMarkdown>
                    </div>
            ))}

            {choices && <ChoiceButtons choices={choices} onPick={handleChoice} />}
            <div ref={bottomRef} />

            <div id="input-area">
                {previewUrl && (
                    pendingFileType === "video"
                        ? <video src={previewUrl} style={{
                            position: "absolute", bottom: "100%", left: 0,
                            maxWidth: "60px", maxHeight: "60px", borderRadius: "8px"
                        }} />
                        : <img src={previewUrl} style={{
                            position: "absolute", bottom: "100%", left: 0,
                            maxWidth: "60px", maxHeight: "60px", borderRadius: "8px"
                        }} />
                )}
                <input
                    id="user-input"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter")
                            handleSend()
                    }}
                    autoComplete="off"
                    placeholder=" Ask something!"
                />
                <button id="send-btn" onClick={handleSend}
                    title="Send message">
                    <i className="fa-solid fa-paper-plane"></i>
                </button>

                <label htmlFor="media-upload" title="Attach file">
                    <i className="fa-solid fa-paperclip"></i>
                </label>
                <input
                    type="file"
                    id="media-upload"
                    accept="image/*,video/*"
                    style={{ display: "none" }}
                    onChange={handleUpload}
                />
            </div>
        </div>
    )
}

export default Chat