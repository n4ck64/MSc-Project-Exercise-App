import { useState } from 'react'
import Chat from './pages/Chat'
import Exercises from './pages/Exercises'
import Plans from './pages/Plans'
import Nutrition from './pages/Nutrition'

function App() {
  const [activeTab, setActiveTab] = useState("chat")
  // bumping this tells Plans to refetch. We bump it (not just switch tabs) only
  // when a new plan is built, so normal tab-clicks keep any in-session progress.
  const [planNonce, setPlanNonce] = useState(0)

  // handed to Chat so its "Plans" link can jump here AND force a fresh load.
  const goToPlans = () => {
    setPlanNonce(n => n + 1)
    setActiveTab("plans")
  }

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
          <Chat goToPlans={goToPlans} />
        </div>
        <div style={{ display: activeTab === "exercises" ? "contents" : "none" }}>
          <Exercises />
        </div>
        <div style={{ display: activeTab === "plans" ? "contents" : "none" }}>
          <Plans refreshSignal={planNonce} />
        </div>
        <div style={{ display: activeTab === "nutrition" ? "contents" : "none" }}>
          <Nutrition />
        </div>

      </div>
    </>

  )
}

export default App

