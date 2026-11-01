"use client";

import { useState } from "react";

import type { Flag, Location, Photo, ReviewRow } from "@/lib/types";

export function PhotoCard({
  photo,
  row,
  onChange,
}: {
  photo: Photo;
  row: ReviewRow;
  onChange: (row: ReviewRow) => void;
}) {
  const [tagText, setTagText] = useState(row.tags.join(", "));
  const location = row.location;
  const alt = photo.altDescription || photo.description || `Photo ${photo.id}`;

  function setLocation(next: Location | null) {
    const empty = !next || (!next.name && !next.city && !next.region && !next.country && next.latitude === null && next.longitude === null);
    onChange({
      ...row,
      location: empty ? null : next,
      locationFlag: empty ? "empty" : "ok",
      locationSource: "human",
      locationConfidence: empty ? 0 : 1,
      locationReason: empty ? "cleared during review" : "edited during review",
    });
  }

  return (
    <article className="card">
      <div className="frame">
        {photo.urls.small ? (
          // eslint-disable-next-line @next/next/no-img-element -- Unsplash already serves a sized JPEG.
          <img src={photo.urls.small} alt={alt} />
        ) : (
          <div className="card-body">{photo.id}</div>
        )}
      </div>
      <div className="card-body">
        <div className="meta">
          <span className="frame-id">{photo.id}</span>
          <span className="quiet">{photo.downloads} downloads</span>
        </div>
        <p className="quiet">{row.collectionTitle}</p>
        <label className="check">
          <input
            type="checkbox"
            checked={row.include}
            onChange={(event) => onChange({ ...row, include: event.target.checked })}
          />
          Apply this photo
        </label>
        <fieldset className={warnClass(row.locationFlag)}>
          <legend>
            Location {row.locationFlag === "ok" ? null : <span className="flag">Check this</span>}
          </legend>
          <label htmlFor={`${photo.id}-name`}>Name</label>
          <input
            id={`${photo.id}-name`}
            value={location?.name ?? ""}
            onChange={(event) => setLocation({ ...(location ?? blankLocation()), name: event.target.value || null })}
          />
          <div className="grid-2">
            <div>
              <label htmlFor={`${photo.id}-city`}>City</label>
              <input
                id={`${photo.id}-city`}
                value={location?.city ?? ""}
                onChange={(event) => setLocation({ ...(location ?? blankLocation()), city: event.target.value || null })}
              />
            </div>
            <div>
              <label htmlFor={`${photo.id}-country`}>Country</label>
              <input
                id={`${photo.id}-country`}
                value={location?.country ?? ""}
                onChange={(event) => setLocation({ ...(location ?? blankLocation()), country: event.target.value || null })}
              />
            </div>
          </div>
          <p className="quiet">{row.locationReason}</p>
        </fieldset>
        <div className={warnClass(row.tagsFlag)}>
          <label htmlFor={`${photo.id}-tags`}>
            Tags {row.tagsFlag === "ok" ? null : <span className="flag">Check this</span>}
          </label>
          <textarea
            id={`${photo.id}-tags`}
            value={tagText}
            onChange={(event) => {
              const text = event.target.value;
              setTagText(text);
              onChange({
                ...row,
                tags: text
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
                tagsFlag: "ok",
                tagsConfidence: 1,
                tagsReason: "edited during review",
              });
            }}
          />
          <p className="quiet">{row.tagsReason}</p>
        </div>
        <div className={warnClass(row.showFlag)}>
          <label className="check">
            <input
              type="checkbox"
              checked={row.showOnProfile}
              onChange={(event) =>
                onChange({
                  ...row,
                  showOnProfile: event.target.checked,
                  showFlag: "ok",
                  showSource: "human",
                  showConfidence: 1,
                  showReason: "edited during review",
                })
              }
            />
            Show on profile {row.showFlag === "ok" ? null : <span className="flag">Check this</span>}
          </label>
          <p className="quiet">{row.showReason}</p>
        </div>
        {row.lastError ? (
          <p className="alert" role="alert">
            {row.lastError}
          </p>
        ) : null}
      </div>
    </article>
  );
}

function warnClass(flag: Flag): string {
  return flag === "review" || flag === "empty" ? "needs-review" : "";
}

function blankLocation(): Location {
  return { name: null, city: null, region: null, country: null, latitude: null, longitude: null };
}
