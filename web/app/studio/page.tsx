import { TripForm } from "@/components/TripForm";

export default function StudioPage() {
  return (
    <main id="content">
      <p className="eyebrow">Trip sheet</p>
      <h1>Where were you?</h1>
      <p className="lede">
        One collection per trip. A day with a single place is filled in. A day with several places is left blank so you can choose.
        Place names come from OpenStreetMap.
      </p>
      <TripForm />
    </main>
  );
}
