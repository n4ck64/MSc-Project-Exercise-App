import { useState } from 'react'
import Chat from './pages/Chat'
import Exercises from './pages/Exercises'
import Plans from './pages/Plans'
import Nutrition from './pages/Nutrition'

function App() {
  const [activeTab, setActiveTab] = useState("chat")

  return (
    <>
      <h1>ReFit</h1>
      <div id="layout">
        <div id="sidebar">
          <div className="sidebar-tab" onClick={() => setActiveTab("chat")}>Chat</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("exercises")}>Exercises</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("plans")}>Plans</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("nutrition")}>Nutrition</div>
          <img id="user-avatar" src="/chad.png" />
        </div>

        <div style={{ display: activeTab === "chat" ? "contents" : "none" }}>
          <Chat />
        </div>
        <div style={{ display: activeTab === "exercises" ? "contents" : "none" }}>
          <Exercises />
        </div>
        <div style={{ display: activeTab === "plans" ? "contents" : "none" }}>
          <Plans />
        </div>
        <div style={{ display: activeTab === "nutrition" ? "contents" : "none" }}>
          <Nutrition />
        </div>

      </div>
    </>

  )
}

export default App

