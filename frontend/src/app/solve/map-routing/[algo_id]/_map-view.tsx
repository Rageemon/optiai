'use client';
/**
 * _map-view.tsx
 * Loaded dynamically (ssr: false) by page.tsx.
 * All Leaflet code lives here — never runs on the server.
 */
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMapEvents, useMap } from 'react-leaflet';
import { useEffect } from 'react';

// ─── Fix webpack‑broken default icons ───────────────────────────────────────
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

export const POI_COLORS: Record<string, string> = {
  restaurant: '#ef4444',
  cafe:       '#f97316',
  park:       '#22c55e',
  museum:     '#8b5cf6',
  hospital:   '#3b82f6',
  bar:        '#ec4899',
  pub:        '#a78bfa',
  fast_food:  '#fb923c',
  default:    '#64748b',
};

function makeDot(color: string, size = 10, border = 2) {
  return L.divIcon({
    className: '',
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;
            background:${color};border:${border}px solid white;
            box-shadow:0 1px 4px rgba(0,0,0,.45)"></div>`,
    iconSize:   [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export const startIcon = makeDot('#22c55e', 16, 3);
export const endIcon   = makeDot('#ef4444', 16, 3);
export const poiIcon   = (type: string) => makeDot(POI_COLORS[type] ?? POI_COLORS.default);

// ─── Sub-components ──────────────────────────────────────────────────────────

function ClickHandler({ onMapClick }: { onMapClick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click: (e) => {
      onMapClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

/** Pan & zoom to fit given bounds whenever coords change */
function FitBounds({ coords }: { coords: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (coords.length >= 2) map.fitBounds(coords, { padding: [50, 50] });
  }, [map, coords]);
  return null;
}

/** Pan to a single point (for when only start or center is known) */
function PanTo({ center, zoom }: { center: [number, number]; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom ?? map.getZoom());
  }, [map, center, zoom]);
  return null;
}

// ─── Exported props types ────────────────────────────────────────────────────

export interface PoiPoint {
  name: string;
  type: string;
  lat: number;
  lng: number;
}

export interface MapViewProps {
  startPos:     [number, number] | null;
  endPos:       [number, number] | null;
  routeCoords:  [number, number][];
  altCoords:    [number, number][];
  pois:         PoiPoint[];
  clickEnabled: boolean;
  onMapClick:   (lat: number, lng: number) => void;
  defaultCenter?: [number, number];
  defaultZoom?:  number;
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function MapView({
  startPos, endPos, routeCoords, altCoords, pois,
  clickEnabled, onMapClick, defaultCenter, defaultZoom,
}: MapViewProps) {
  // Determine what to fit
  const fitCoords: [number, number][] = [
    ...routeCoords,
    ...(startPos ? [startPos] : []),
    ...(endPos   ? [endPos]   : []),
  ];

  // Default center: India (neutral for the user's context) if nothing else
  const center = defaultCenter ?? [20.5937, 78.9629];
  const zoom   = defaultZoom ?? 5;

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      style={{ height: '100%', width: '100%' }}
      className={clickEnabled ? '!cursor-crosshair' : ''}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* Always handle clicks */}
      <ClickHandler onMapClick={onMapClick} />

      {/* Fit to route + markers */}
      {fitCoords.length >= 2 && <FitBounds coords={fitCoords} />}

      {/* If only one marker, pan to it */}
      {fitCoords.length === 1 && <PanTo center={fitCoords[0]} zoom={14} />}

      {/* Baseline (grey dashed) */}
      {altCoords.length > 1 && (
        <Polyline
          positions={altCoords}
          pathOptions={{ color: '#94a3b8', weight: 3, dashArray: '7 7', opacity: 0.65 }}
        />
      )}

      {/* Optimised route (blue) */}
      {routeCoords.length > 1 && (
        <Polyline
          positions={routeCoords}
          pathOptions={{ color: '#3b82f6', weight: 5, opacity: 0.9 }}
        />
      )}

      {/* POI markers */}
      {pois.map((poi, i) => (
        <Marker key={i} position={[poi.lat, poi.lng]} icon={poiIcon(poi.type)}>
          <Popup>
            <strong className="text-sm">{poi.name}</strong>
            <br />
            <span style={{ color: POI_COLORS[poi.type] ?? POI_COLORS.default, textTransform: 'capitalize' }}>
              {poi.type}
            </span>
          </Popup>
        </Marker>
      ))}

      {/* Start / end pins */}
      {startPos && <Marker position={startPos} icon={startIcon}><Popup>Start</Popup></Marker>}
      {endPos   && <Marker position={endPos}   icon={endIcon}  ><Popup>End</Popup></Marker>}
    </MapContainer>
  );
}
