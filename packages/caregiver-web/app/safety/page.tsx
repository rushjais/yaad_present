// C5 — Safety view: set home + safe-zone, ordered contacts, alert history
// Wires to POST /location/ping — reassure + alert a human, NEVER navigate.
export default function SafetyPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Safety</h1>
      <p className="text-stone-500 text-sm">Geofence, contacts, and alert history — coming in C5.</p>
    </div>
  );
}
