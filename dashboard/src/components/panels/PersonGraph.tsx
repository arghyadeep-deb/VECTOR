import { useEffect, useState } from "react";

interface PersonNode {
  id?: string;
  person_id?: string;
  name: string;
  trust_score?: number;
}

export function PersonGraph() {
  const [persons, setPersons] = useState<PersonNode[]>([]);
  const [selected, setSelected] = useState<PersonNode | null>(null);

  const loadPersons = async () => {
    const res = await fetch("/brain/persons");
    const data = await res.json();
    setPersons(data.persons || []);
  };

  const updateTrust = async (person: PersonNode, delta: number) => {
    const id = person.id || person.person_id;
    await fetch(`/brain/persons/${id}/trust`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta }),
    });
    await loadPersons();
  };

  const updateBelief = async (person: PersonNode) => {
    const id = person.id || person.person_id;
    await fetch(`/brain/persons/${id}/belief`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "dashboard_note", value: "reviewed", confidence: 0.7 }),
    });
  };

  useEffect(() => {
    void loadPersons();
  }, []);

  return (
    <section className="panel person-graph">
      <h2>Person Graph</h2>
      <svg viewBox="0 0 420 220" role="img" aria-label="Person relationship graph">
        <circle cx="210" cy="110" r="34" />
        <text x="210" y="114" textAnchor="middle">VECTOR</text>
        {persons.map((person, index) => {
          const angle = (Math.PI * 2 * index) / Math.max(persons.length, 1);
          const x = 210 + Math.cos(angle) * 140;
          const y = 110 + Math.sin(angle) * 76;
          return (
            <g key={person.id || person.person_id || person.name} onClick={() => setSelected(person)}>
              <line x1="210" y1="110" x2={x} y2={y} />
              <circle cx={x} cy={y} r="24" />
              <text x={x} y={y + 4} textAnchor="middle">{person.name}</text>
            </g>
          );
        })}
      </svg>
      {selected && (
        <div className="person-actions">
          <button onClick={() => void updateTrust(selected, 0.05)}>Raise Trust</button>
          <button onClick={() => void updateTrust(selected, -0.05)}>Lower Trust</button>
          <button onClick={() => void updateBelief(selected)}>Save Belief</button>
        </div>
      )}
    </section>
  );
}
