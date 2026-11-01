export type Location = {
  name: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type Photo = {
  id: string;
  slug: string;
  createdAt: string;
  width: number;
  height: number;
  description: string | null;
  altDescription: string | null;
  location: Location | null;
  tags: string[];
  downloads: number;
  likes: number;
  views: number;
  camera: string | null;
  showOnProfile: boolean;
  showOnProfileKnown: boolean;
  urls: { small?: string; regular?: string };
  collections: { id: string; title: string }[];
  capturedAt: string | null;
};

export type Place = {
  name: string;
  city: string | null;
  region: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type TripDay = {
  date: string;
  tags: string[];
  places: Place[];
};

export type Trip = {
  name: string;
  collection: string;
  description: string;
  template: string | null;
  tags: string[];
  days: TripDay[];
};

export type Flag = "ok" | "review" | "empty";

export type Suggestion<T> = {
  value: T;
  confidence: number;
  source: string;
  flag: Flag;
  reason: string;
};

export type ReviewRow = {
  photoId: string;
  include: boolean;
  location: Location | null;
  locationConfidence: number;
  locationFlag: Flag;
  locationSource: string;
  locationReason: string;
  tags: string[];
  tagsConfidence: number;
  tagsFlag: Flag;
  tagsReason: string;
  description: string;
  descriptionConfidence: number;
  descriptionFlag: Flag;
  descriptionSource: string;
  showOnProfile: boolean;
  showConfidence: number;
  showFlag: Flag;
  showSource: string;
  showReason: string;
  collectionTitle: string;
  collectionDescription: string;
  notes: string;
  lastStatus: string;
  lastError: string;
};

export type StoredPlan = {
  id: string;
  createdAt: string;
  title: string;
  trip: Trip;
  photos: Photo[];
  rows: ReviewRow[];
  collections: { id: string; title: string }[];
};

export type PhotoUpdate = {
  description?: string;
  showOnProfile?: boolean;
  tags?: string[];
  location?: {
    name: string | null;
    city: string | null;
    country: string | null;
    latitude: number | null;
    longitude: number | null;
  };
};

export type ApplyResult = {
  photoId: string;
  status: "updated" | "skipped" | "failed" | "dry-run";
  operations: string[];
  error: string;
  mode: "live" | "fixture";
};
