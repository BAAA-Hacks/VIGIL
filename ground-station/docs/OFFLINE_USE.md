# Offline mission use

Keep the locally installed dashboard, thermal relay, and Python detector running. Internet is not required for the camera Wi-Fi or local Socket.IO feed. Keep model weights and Python dependencies installed before deployment.

Before leaving internet coverage, open **Offline maps** on the map, select the map layer, and choose **Save map area**. This saves the visible geographic area at the current integer zoom, one level below, and two levels above (maximum level 19). Repeat for other layers and mission areas. Up to 500 tiles per save; zoom in if necessary. Ordinary map viewing also saves tiles automatically. Unvisited/unsaved areas and zoom levels still require internet. Provider credits remain visible.

Tiles and successful point elevation readings persist in `.vigil-offline/` on the ground computer, independent of browser cache and app restarts. A saved point reading only covers its coordinate rounded to five decimal places; it is not a terrain dataset. No elevation is fabricated when coverage is missing.

For terrain coverage at new coordinates, use **Import terrain** to load a JSON grid in the following format. Values are meters above sea level and must use a datum compatible with the drone altitude. Rows run south to north; columns west to east. Both steps are positive degrees, cells may be null for missing coverage, maximum 512 rows/columns. Bilinear interpolation stays within coverage. Imported terrain serves manual-pin elevation, reference-ground lookup, and live geolocation. Restart/reload restores the imported grid.

```json
{"south":34.05,"west":-118.25,"latitudeStep":0.001,"longitudeStep":0.001,"elevations":[[100,101],[102,103]]}
```

The numbers above demonstrate the file structure only; they are not mission terrain. Obtain real elevation data for the mission area before field use.

Start offline with existing local installations: `npm run dev` (or a previously completed production build via `npm start`), `npm run thermal:relay`, and `python -m AI.scripts.lepton_live --socket-url http://127.0.0.1:5000` from the repository root. Connect to Lepton-Camera Wi-Fi. The local app server must remain running; this is not a standalone browser installation.
