import { useState, useEffect } from 'react'
import Chat from './pages/Chat'
import Exercises from './pages/Exercises'
import Plans from './pages/Plans'
import Nutrition from './pages/Nutrition'

type User = { user_id: number, full_name: string }

function App() {
  const [activeTab, setActiveTab] = useState("chat")
  // bumping this tells Plans to refetch. We bump it (not just switch tabs) only
  // when a new plan is built or edited, so normal tab-clicks keep any in-session progress.
  const [planNonce, setPlanNonce] = useState(0)
  // Nutrition refetches on every switch TO the tab, not just when chat logs food:
  // the page is mounted permanently behind display:none, so without this it would
  // still show whatever it fetched on page load.
  const [nutritionNonce, setNutritionNonce] = useState(0)

  // dev-only user switcher — no auth yet, so this is how multi-user testing
  // picks which seeded persona (evaluation/personas.md) chat/plans act as.
  const [users, setUsers] = useState<User[]>([])
  const [userId, setUserId] = useState(1)

  useEffect(() => {
    fetch("http://localhost:8000/users")
      .then(res => res.json())
      .then(setUsers)
  }, [])

  // handed to Chat so its "Plans" link can jump here AND force a fresh load.
  const goToPlans = () => {
    setPlanNonce(n => n + 1)
    setActiveTab("plans")
  }

  // handed to Chat so a confirmed food log can link straight to the fresh totals
  const goToNutrition = () => {
    setNutritionNonce(n => n + 1)
    setActiveTab("nutrition")
  }

  return (
    <>
      <h1>ReFit</h1>
      <div id="layout">
        <div id="sidebar">
          <div className="sidebar-tab" onClick={() => setActiveTab("chat")}>Chat</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("exercises")}>Exercises</div>
          <div className="sidebar-tab" onClick={() => setActiveTab("plans")}>Plans</div>
          <div className="sidebar-tab" onClick={goToNutrition}>Nutrition</div>
          <select value={userId} onChange={e => setUserId(Number(e.target.value))}
            title="Switch test user (dev only)"
            style={{ marginTop: "20px", width: "80%", marginLeft: "20px" }}>
            {users.map(u => (
              <option key={u.user_id} value={u.user_id}>{u.full_name}</option>
            ))}
          </select>
          <img id="user-avatar" src="/chad.png" />
        </div>

        <div style={{ display: activeTab === "chat" ? "contents" : "none" }}>
          <Chat goToPlans={goToPlans} goToNutrition={goToNutrition} userId={userId} />
        </div>
        <div style={{ display: activeTab === "exercises" ? "contents" : "none" }}>
          <Exercises />
        </div>
        <div style={{ display: activeTab === "plans" ? "contents" : "none" }}>
          <Plans refreshSignal={planNonce} userId={userId} />
        </div>
        <div style={{ display: activeTab === "nutrition" ? "contents" : "none" }}>
          <Nutrition userId={userId} refreshSignal={nutritionNonce} />
        </div>

      </div>
    </>

  )
}

export default App

