import { useState, useEffect } from 'react'

// Payloads from GET /nutrition/day and /nutrition/week (retrieval.day_view / week_view).
type Gap = {
    consumed: number
    target: number
    limit_type: "target" | "min" | "max"
    remaining: number
}
type Target = { value: number; limit_type: string }
type LogEntry = { log_id: number; food_name: string; grams: number; energy_kcal: number }

type DayPayload = {
    date: string
    entries: LogEntry[]
    totals: Record<string, number>
    targets: Record<string, Target>
    gaps: Record<string, Gap>          // targeted nutrients only — see 'untargeted'
    untargeted: string[]               // tracked but not scored (retrieval.UNTARGETED_NUTRIENTS)
}
type WeekPayload = {
    days: { date: string; totals: Record<string, number> }[]
    average: Record<string, number>
    targets: Record<string, Target>
    average_gaps: Record<string, Gap>
    untargeted: string[]
}
type FoodHit = { food_id: number; food_name: string; energy_kcal: number }

const API = "http://localhost:8000"

const NUTRIENT_LABELS: Record<string, string> = {
    energy_kcal: "Energy", protein_g: "Protein", fat_g: "Fat",
    carb_g: "Carbs", fibre_g: "Fibre", total_sugars_g: "Total sugars",
}
const NUTRIENT_ORDER = ["energy_kcal", "protein_g", "carb_g", "fat_g", "fibre_g"]
const SHORT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

// Split fill from text the way DIFFICULTY_COLORS does in Exercises.tsx: its amber
// (#854f0b) is a TEXT colour meant for a pale pill, and reads brown as a solid bar,
// so the bar uses the gold Plans.tsx already highlights with while the label keeps
// the darker, more readable tone.
const GREEN = { fill: "#3b6d11", text: "#3b6d11" }
const AMBER = { fill: "#c9a227", text: "#854f0b" }
const RED = { fill: "#a32d2d", text: "#a32d2d" }
const CHART_HEIGHT = 120

const unitFor = (nutrient: string) => nutrient === "energy_kcal" ? " kcal" : "g"
const labelFor = (nutrient: string) => NUTRIENT_LABELS[nutrient] ?? nutrient

// append a time so the ISO date is parsed locally, not shifted a day by UTC
const dayLabel = (iso: string) => SHORT_DAYS[new Date(`${iso}T00:00:00`).getDay()]


// The limit_type branch, and the whole reason this page isn't a generic tracker:
// 'max' nutrients are a budget spent down (green while under, red past zero),
// 'min'/'target' fill toward a goal (amber while short, green once reached).
function barState(gap: Gap) {
    const pct = gap.target > 0
        ? Math.min(100, (gap.consumed / gap.target) * 100)   // caps the BAR, never the number
        : 0
    if (gap.limit_type === "max") {
        return gap.remaining < 0
            ? { pct: 100, colour: RED, note: `${Math.abs(gap.remaining)} over limit` }
            : { pct, colour: GREEN, note: `${gap.remaining} left` }
    }
    return gap.remaining > 0
        ? { pct, colour: AMBER, note: `${gap.remaining} to go` }
        : { pct: 100, colour: GREEN, note: "target met" }
}


// ── one nutrient against its target. Shared by today and the weekly average,
// which is why the backend gives both the same Gap shape.
function NutrientBar({ nutrient, gap }: { nutrient: string; gap: Gap }) {
    const { pct, colour, note } = barState(gap)
    return (
        <div style={{ marginBottom: "10px" }}>
            <div style={{
                display: "flex", justifyContent: "space-between",
                fontSize: "13px", marginBottom: "3px",
            }}>
                <span style={{ fontWeight: 500 }}>{labelFor(nutrient)}</span>
                <span style={{ color: "grey" }}>
                    {gap.consumed} / {gap.target}{unitFor(nutrient)}
                    {" · "}<span style={{ color: colour.text, fontWeight: 500 }}>{note}</span>
                </span>
            </div>
            {/* track is the card yellow, not the page yellow — body is rgb(255,255,232),
                so an empty bar would be invisible against it */}
            <div style={{
                height: "8px", borderRadius: "6px",
                background: "rgb(255,255,206)", overflow: "hidden",
            }}>
                <div style={{ width: `${pct}%`, height: "100%", background: colour.fill }} />
            </div>
        </div>
    )
}


// ── a tracked-but-unscored nutrient: no bar, no colour, just the number
function UntargetedRow({ nutrient, amount }: { nutrient: string; amount: number }) {
    return (
        <div title="No comparable UK guideline — the food data reports total sugars, which
includes the intrinsic sugars in fruit and milk that the PHE free-sugars target excludes."
            style={{
                display: "flex", justifyContent: "space-between", fontSize: "13px",
                color: "grey", padding: "7px 0", borderTop: "1px solid rgba(0,0,0,0.07)",
            }}>
            <span>{labelFor(nutrient)}</span>
            <span>
                {amount}{unitFor(nutrient)}
                <span style={{ fontSize: "11px" }}> · not scored</span>
            </span>
        </div>
    )
}


// ── search the food database and log a portion of the chosen result
function FoodSearch({ onAdd }: { onAdd: (foodId: number, grams: number) => void }) {
    const [query, setQuery] = useState("")
    const [selected, setSelected] = useState<FoodHit | null>(null)
    const [grams, setGrams] = useState(100)
    // Results carry the query they came from, so which ones are current is DERIVED
    // rather than cleared. Clearing them in the effect body below would trigger a
    // cascading render (react-hooks/set-state-in-effect).
    const [results, setResults] = useState<{ query: string; hits: FoodHit[] }>(
        { query: "", hits: [] })
    const hits = results.query === query ? results.hits : []

    // Debounced: every keystroke would otherwise fire an embedding search server-side.
    // The cleanup cancels the pending timer AND ignores an in-flight reply we no longer
    // want, so a slow early request can't overwrite a newer one.
    useEffect(() => {
        if (query.trim().length < 3) return
        let cancelled = false
        const timer = setTimeout(async () => {
            const res = await fetch(
                `${API}/nutrition/foods/search?q=${encodeURIComponent(query)}`)
            const found = await res.json()
            if (!cancelled) setResults({ query, hits: found })
        }, 300)
        return () => { cancelled = true; clearTimeout(timer) }
    }, [query])

    function add() {
        if (!selected) return
        onAdd(selected.food_id, grams)
        setSelected(null)
        setQuery("")        // empties 'hits' on its own, since they no longer match
        setGrams(100)
    }

    return (
        <div style={{ marginBottom: "18px" }}>
            <input value={query} onChange={event => setQuery(event.target.value)}
                placeholder="Search a food to log…"
                style={{
                    width: "100%", padding: "8px 12px", borderRadius: "8px",
                    border: "none", background: "rgb(255,255,206)", fontSize: "14px",
                    boxSizing: "border-box",
                }} />

            {!selected && hits.map(hit => (
                <div key={hit.food_id} onClick={() => setSelected(hit)}
                    style={{
                        padding: "7px 12px", borderRadius: "8px", cursor: "pointer",
                        fontSize: "13px", background: "rgb(255,255,206)",
                        marginTop: "5px",
                    }}>
                    {hit.food_name}
                    <span style={{ color: "grey", fontSize: "11px" }}>
                        {" · "}{hit.energy_kcal} kcal/100g
                    </span>
                </div>
            ))}

            {selected && (
                <div style={{
                    marginTop: "8px", display: "flex", alignItems: "center",
                    gap: "8px", flexWrap: "wrap", background: "rgb(255,255,206)",
                    borderRadius: "10px", padding: "8px 12px",
                }}>
                    <span style={{ flex: 1, minWidth: "140px", fontSize: "13px" }}>
                        {selected.food_name}
                    </span>
                    <input type="number" min={1} value={grams}
                        onChange={event => setGrams(Number(event.target.value))}
                        style={{
                            width: "56px", padding: "4px 6px", borderRadius: "6px",
                            border: "none", background: "rgb(255,255,232)",
                            fontSize: "13px", textAlign: "center",
                        }} />
                    <span style={{ color: "grey", fontSize: "12px" }}>g</span>
                    <button className="choice-btn" onClick={add}>Add</button>
                    <button className="choice-btn" onClick={() => setSelected(null)}>Cancel</button>
                </div>
            )}
        </div>
    )
}


function TodayView({ day, onAdd, onRemove }: {
    day: DayPayload
    onAdd: (foodId: number, grams: number) => void
    onRemove: (logId: number) => void
}) {
    const scored = NUTRIENT_ORDER.filter(nutrient => day.gaps[nutrient])

    return (
        <div>
            <FoodSearch onAdd={onAdd} />

            {scored.length === 0
                ? <p style={{ color: "grey", fontSize: "13px" }}>
                    No date of birth on file for this user, so daily targets can't be worked out.
                </p>
                : scored.map(nutrient => (
                    <NutrientBar key={nutrient} nutrient={nutrient} gap={day.gaps[nutrient]} />
                ))}

            {day.untargeted.map(nutrient => (
                <UntargetedRow key={nutrient} nutrient={nutrient} amount={day.totals[nutrient]} />
            ))}

            <h3 style={{ margin: "20px 0 8px", fontSize: "15px" }}>Logged today</h3>
            {day.entries.length === 0
                ? <div style={{ color: "grey", fontStyle: "italic", fontSize: "13px" }}>
                    Nothing logged yet.
                </div>
                : day.entries.map(entry => (
                    <div key={entry.log_id} style={{
                        display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap",
                        background: "rgb(255,255,206)", borderRadius: "10px",
                        padding: "8px 12px", marginBottom: "6px",
                    }}>
                        <span style={{ flex: 1, minWidth: "120px", fontSize: "13px" }}>
                            {entry.food_name}
                        </span>
                        <span style={{ color: "grey", fontSize: "12px" }}>{entry.grams}g</span>
                        <span style={{ color: "grey", fontSize: "12px" }}>{entry.energy_kcal} kcal</span>
                        <button onClick={() => onRemove(entry.log_id)} title="Remove"
                            style={{
                                border: "none", background: "transparent", cursor: "pointer",
                                color: "grey", fontSize: "17px", lineHeight: 1, padding: "0 2px",
                            }}>×</button>
                    </div>
                ))}
        </div>
    )
}


function WeekTab({ week }: { week: WeekPayload }) {
    const target = week.targets.energy_kcal?.value ?? 0
    // scale to whichever is taller, so the guideline line always sits on the chart
    const scaleMax = Math.max(target, ...week.days.map(day => day.totals.energy_kcal)) || 1
    const scored = NUTRIENT_ORDER.filter(nutrient => week.average_gaps[nutrient])

    return (
        <div>
            <h3 style={{ margin: "0 0 4px", fontSize: "15px" }}>Energy, last 7 days</h3>
            <p style={{ margin: "0 0 12px", fontSize: "12px", color: "grey" }}>
                {target > 0 && `Dashed line is the daily guideline (${target} kcal).`}
            </p>

            <div style={{
                display: "flex", alignItems: "flex-end", gap: "6px",
                height: `${CHART_HEIGHT}px`, position: "relative",
            }}>
                {target > 0 && (
                    <div style={{
                        position: "absolute", left: 0, right: 0,
                        bottom: `${(target / scaleMax) * 100}%`,
                        borderTop: "1px dashed #c9a227",
                    }} />
                )}
                {/* every day the same gold: individual days are deliberately NOT scored
                    pass/fail, only the 7-day average below is */}
                {week.days.map(day => (
                    <div key={day.date} title={`${day.totals.energy_kcal} kcal`}
                        style={{
                            flex: 1, alignSelf: "flex-end",
                            height: `${(day.totals.energy_kcal / scaleMax) * 100}%`,
                            minHeight: day.totals.energy_kcal > 0 ? "3px" : "0",
                            background: AMBER.fill, borderRadius: "6px 6px 0 0",
                        }} />
                ))}
            </div>

            <div style={{ display: "flex", gap: "6px", marginTop: "5px", marginBottom: "22px" }}>
                {week.days.map(day => (
                    <div key={day.date} style={{
                        flex: 1, textAlign: "center", fontSize: "11px", color: "grey",
                    }}>{dayLabel(day.date)}</div>
                ))}
            </div>

            <h3 style={{ margin: "0 0 4px", fontSize: "15px" }}>7-day average</h3>
            <p style={{ margin: "0 0 12px", fontSize: "12px", color: "grey" }}>
                Scored as an average rather than day by day — the UK figures are population
                average intakes, not daily pass/fail limits.
            </p>
            {scored.map(nutrient => (
                <NutrientBar key={nutrient} nutrient={nutrient} gap={week.average_gaps[nutrient]} />
            ))}
            {week.untargeted.map(nutrient => (
                <UntargetedRow key={nutrient} nutrient={nutrient} amount={week.average[nutrient]} />
            ))}
        </div>
    )
}


function Nutrition({ userId, refreshSignal }: { userId: number; refreshSignal: number }) {
    const [day, setDay] = useState<DayPayload | null>(null)
    const [week, setWeek] = useState<WeekPayload | null>(null)
    const [view, setView] = useState<"today" | "week">("today")

    useEffect(() => {
        async function load() {
            const [dayRes, weekRes] = await Promise.all([
                fetch(`${API}/nutrition/day?user_id=${userId}`),
                fetch(`${API}/nutrition/week?user_id=${userId}`),
            ])
            setDay(await dayRes.json())
            setWeek(await weekRes.json())
        }
        load()
        // refreshSignal: App bumps it on every switch to this tab, so a food logged
        // through chat (or on another device) shows up rather than the load-time copy
    }, [userId, refreshSignal])

    async function refreshWeek() {
        const res = await fetch(`${API}/nutrition/week?user_id=${userId}`)
        setWeek(await res.json())
    }

    // The log lives in Postgres, so 'day' is a mirror of server state: both writers
    // replace it wholesale with what the server returned rather than patching it
    // locally, which would drift the moment a total was recomputed.
    async function onAdd(foodId: number, grams: number) {
        const res = await fetch(`${API}/nutrition/log`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, food_id: foodId, grams }),
        })
        if (!res.ok) return   // fetch does not throw on 404 — check res.ok
        setDay(await res.json())
        refreshWeek()         // today's bar in the 7-day chart just moved
    }

    async function onRemove(logId: number) {
        const res = await fetch(`${API}/nutrition/log/${logId}?user_id=${userId}`,
            { method: "DELETE" })
        if (!res.ok) return
        setDay(await res.json())
        refreshWeek()
    }

    if (!day || !week) {
        return <div id="chat-window"><h2>Nutrition</h2></div>
    }

    return (
        <div id="chat-window">
            <div style={{ marginBottom: "14px", display: "flex", gap: "8px" }}>
                <button className="choice-btn"
                    style={{ fontWeight: view === "today" ? 600 : 400 }}
                    onClick={() => setView("today")}>Today</button>
                <button className="choice-btn"
                    style={{ fontWeight: view === "week" ? 600 : 400 }}
                    onClick={() => setView("week")}>Week</button>
            </div>

            {view === "today" && <TodayView day={day} onAdd={onAdd} onRemove={onRemove} />}
            {view === "week" && <WeekTab week={week} />}
        </div>
    )
}

export default Nutrition
