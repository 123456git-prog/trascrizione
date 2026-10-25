import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { formatTime } from "../api.js";
import { Icon } from "./ui.jsx";

const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.75];

// Player fisso in basso; espone l'elemento <audio> al genitore per i salti dalla trascrizione.
const Player = forwardRef(function Player({ src, duration: knownDuration, onTime }, ref) {
  const el = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(knownDuration || 0);
  const [speed, setSpeed] = useState(1);

  useImperativeHandle(ref, () => el.current, []);

  useEffect(() => {
    const a = el.current;
    const onTimeUpdate = () => {
      setTime(a.currentTime);
      onTime?.(a.currentTime);
    };
    const handlers = {
      timeupdate: onTimeUpdate,
      seeked: onTimeUpdate,
      play: () => setPlaying(true),
      pause: () => setPlaying(false),
      loadedmetadata: () => isFinite(a.duration) && setDuration(a.duration),
    };
    Object.entries(handlers).forEach(([k, f]) => a.addEventListener(k, f));
    return () => Object.entries(handlers).forEach(([k, f]) => a.removeEventListener(k, f));
  }, [onTime]);

  const skip = (d) => (el.current.currentTime = Math.max(0, Math.min(duration, el.current.currentTime + d)));

  function cycleSpeed() {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    el.current.playbackRate = next;
    setSpeed(next);
  }

  return (
    <div className="player">
      <audio ref={el} src={src} preload="metadata" />
      <input
        className="seek"
        type="range"
        min="0"
        max={duration || 0}
        step="0.1"
        value={time}
        onChange={(e) => (el.current.currentTime = Number(e.target.value))}
        aria-label="Posizione"
        style={{ "--pct": `${duration ? (time / duration) * 100 : 0}%` }}
      />
      <div className="player-row">
        <span className="small mono">{formatTime(time)}</span>
        <div className="player-buttons">
          <button className="icon-btn" onClick={() => skip(-15)} aria-label="Indietro 15 secondi">
            <Icon name="rewind" />
          </button>
          <button className="play-btn" onClick={() => (playing ? el.current.pause() : el.current.play())} aria-label={playing ? "Pausa" : "Riproduci"}>
            <Icon name={playing ? "pause" : "play"} size={26} />
          </button>
          <button className="icon-btn" onClick={() => skip(15)} aria-label="Avanti 15 secondi">
            <Icon name="forward" />
          </button>
        </div>
        <button className="speed small mono" onClick={cycleSpeed} aria-label="Velocità">
          {speed}×
        </button>
      </div>
    </div>
  );
});

export default Player;
