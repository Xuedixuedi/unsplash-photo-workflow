import type { Trip } from "./types";

/** Same itinerary as `trips/example-jiuzhaigou.yaml`. Two places make the day ambiguous. */
export const EXAMPLE_TRIP: Trip = {
  name: "Jiuzhaigou Autumn",
  collection: "Jiuzhaigou Autumn 2026",
  description: "Autumn color in Jiuzhaigou Valley, Sichuan, China.",
  template: "mountain-autumn",
  tags: ["jiuzhaigou", "autumn landscape", "nature photography", "travel photography"],
  days: [
    {
      date: "2026-10-31",
      tags: ["colorful lakes"],
      places: [
        {
          name: "Five Flower Lake",
          city: "Jiuzhaigou County",
          region: "Ngawa",
          country: "China",
          latitude: 33.215,
          longitude: 103.917,
        },
        {
          name: "Pearl Shoals",
          city: "Jiuzhaigou County",
          region: "Ngawa",
          country: "China",
          latitude: 33.2,
          longitude: 103.9,
        },
      ],
    },
  ],
};
