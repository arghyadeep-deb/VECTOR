import { useEffect, useState } from "react";
import { DecisionTrace, type DecisionEvent } from "./components/panels/DecisionTrace";
import { PersonGraph } from "./components/panels/PersonGraph";

type StateEvent = {
  type: "state_ready" | "state_event";
  event_type?: string;
  data?: any;
};

export default function App() {
  const [decisions, setDecisions] = useState<DecisionEvent[]>([]);
  const [events, setEvents] = useState<StateEvent[]>([]);
  const [panel, setPanel] = useState<'overview' | 'persons'>('overview');

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/state`);
    ws.onmessage = (message) => {
      const event: StateEvent = JSON.parse(message.data);
      setEvents((prev) => [event, ...prev].slice(0, 20));
      if (event.type === "state_event" && event.event_type === "decision_made") {
        setDecisions((prev) => [event.data as DecisionEvent, ...prev].slice(0, 20));
      }
      if (event.type === "state_event" && event.event_type === "hypothesis_surfaced") {
        setEvents((prev) => [event, ...prev].slice(0, 20));
      }
    };
    return () => ws.close();
  }, []);

  return (
    <main className="vector-dashboard">
      <nav>
        <button onClick={() => setPanel('overview')}>Overview</button>
        <button onClick={() => setPanel('persons')}>Persons</button>
      </nav>
      {panel === 'persons' ? <PersonGraph /> : <DecisionTrace decisions={decisions} />}
      <aside>
        {events.map((event, index) => (
          <div key={`${event.event_type}-${index}`}>{event.event_type || event.type}</div>
        ))}
      </aside>
    </main>
  );
}
