'use client'

/**
 * LeafletMap.tsx
 * -----------
 * Real-world interactive map component powered by Leaflet + OpenStreetMap tiles.
 *
 * IMPORTANT: This file must be imported with `dynamic(..., { ssr: false })`
 * from the parent page because Leaflet accesses `window` at import time.
 */

import { useEffect } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// ---------------------------------------------------------------------------
// Custom SVG div-icons (avoids Leaflet's broken default asset URLs in bundlers)
// ---------------------------------------------------------------------------

function makePinIcon(color: string, label: string) {
  return L.divIcon({
    html: `
      <div style="position:relative;width:28px;height:36px;cursor:pointer">
        <svg viewBox="0 0 28 36" xmlns="http://www.w3.org/2000/svg" width="28" height="36">
          <path d="M14 0C6.27 0 0 6.27 0 14c0 9.63 14 22 14 22S28 23.63 28 14C28 6.27 21.73 0 14 0z"
                fill="${color}" stroke="white" stroke-width="2"/>
          <circle cx="14" cy="14" r="6" fill="white" fill-opacity="0.9"/>
          <text x="14" y="18" text-anchor="middle" font-size="9" font-weight="bold" fill="${color}">${label}</text>
        </svg>
      </div>`,
    iconSize: [28, 36],
    iconAnchor: [14, 36],
    popupAnchor: [0, -36],
    className: '',
  })
}

function makePoiIcon(color: string) {
  return L.divIcon({
    html: `<div style="width:10px;height:10px;background:${color};border-radius:50%;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.4)"></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
    className: '',
  })
}

const START_ICON = makePinIcon('#16a34a', 'A')
const END_ICON   = makePinIcon('#dc2626', 'B')

const POI_COLORS: Record<string, string> = {
  restaurant: '#f97316',
  cafe:       '#a855f7',
  park:       '#22c55e',
  museum:     '#3b82f6',
  hospital:   '#ef4444',
  bar:        '#eab308',
  pub:        '#f59e0b',
  fast_food:  '#fb923c',
  garden:     '#4ade80',
  hotel:      '#8b5cf6',
  pharmacy:   '#06b6d4',
  supermarket:'#64748b',
  default:    '#6b7280',
}

// ---------------------------------------------------------------------------
// Map click handler inner component
// ---------------------------------------------------------------------------

function ClickHandler({
  clickMode,
  onMapClick,
}: {
  clickMode: 'start' | 'end' | null
  onMapClick: (lat: number, lng: number) => void
}) {
  const map = useMap()

  useEffect(() => {
    map.getContainer().style.cursor = clickMode ? 'crosshair' : ''
  }, [clickMode, map])

  useMapEvents({
    click(e) {
      if (clickMode) {
        onMapClick(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

// ---------------------------------------------------------------------------
// Auto-fit bounds when route data changes
// ---------------------------------------------------------------------------

function BoundsFitter({ bounds }: { bounds: [number, number][] | null }) {
  const map = useMap()
  useEffect(() => {
    if (bounds && bounds.length >= 2) {
      map.fitBounds(bounds as L.LatLngBoundsExpression, { padding: [40, 40] })
    }
  }, [bounds, map])
  return null
}

// ---------------------------------------------------------------------------
// Main map component
// ---------------------------------------------------------------------------

export interface LeafletMapProps {
  startLatLng:    [number, number] | null
  endLatLng:      [number, number] | null
  optimizedRoute: [number, number][]
  baselineRoute:  [number, number][]
  pois:           Array<{ name: string; type: string; lat: number; lng: number }>
  onMapClick:     (lat: number, lng: number) => void
  clickMode:      'start' | 'end' | null
}

export default function LeafletMap({
  startLatLng,
  endLatLng,
  optimizedRoute,
  baselineRoute,
  pois,
  onMapClick,
  clickMode,
}: LeafletMapProps) {
  // Default centre: New York City
  const defaultCenter: [number, number] = [40.7549, -73.984]
  const defaultZoom = 13

  // Compute bounds for auto-fit
  const allRoutePoints = [...optimizedRoute, ...baselineRoute]
  const fitBounds: [number, number][] | null =
    allRoutePoints.length >= 2 ? allRoutePoints : null

  return (
    <MapContainer
      center={defaultCenter}
      zoom={defaultZoom}
      style={{ height: '100%', width: '100%', borderRadius: '0.5rem' }}
      zoomControl={true}
    >
      {/* OpenStreetMap tile layer — free, no API key */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <ClickHandler clickMode={clickMode} onMapClick={onMapClick} />
      {fitBounds && <BoundsFitter bounds={fitBounds} />}

      {/* Baseline (shortest) route — grey dashed */}
      {baselineRoute.length > 1 && (
        <Polyline
          positions={baselineRoute}
          pathOptions={{ color: '#9ca3af', weight: 4, dashArray: '8,6', opacity: 0.7 }}
        />
      )}

      {/* Optimised route — blue solid */}
      {optimizedRoute.length > 1 && (
        <Polyline
          positions={optimizedRoute}
          pathOptions={{ color: '#2563eb', weight: 5, opacity: 0.9 }}
        />
      )}

      {/* POI markers */}
      {pois.map((poi, i) => (
        <Marker
          key={`poi-${i}`}
          position={[poi.lat, poi.lng]}
          icon={makePoiIcon(POI_COLORS[poi.type] ?? POI_COLORS.default)}
        >
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">{poi.name}</div>
              <div className="text-gray-500 capitalize">{poi.type.replace('_', ' ')}</div>
            </div>
          </Popup>
        </Marker>
      ))}

      {/* Start marker */}
      {startLatLng && (
        <Marker position={startLatLng} icon={START_ICON}>
          <Popup>
            <div className="text-sm font-semibold text-green-700">Start</div>
            <div className="text-xs text-gray-500">
              {startLatLng[0].toFixed(5)}, {startLatLng[1].toFixed(5)}
            </div>
          </Popup>
        </Marker>
      )}

      {/* End marker */}
      {endLatLng && (
        <Marker position={endLatLng} icon={END_ICON}>
          <Popup>
            <div className="text-sm font-semibold text-red-700">Destination</div>
            <div className="text-xs text-gray-500">
              {endLatLng[0].toFixed(5)}, {endLatLng[1].toFixed(5)}
            </div>
          </Popup>
        </Marker>
      )}
    </MapContainer>
  )
}
