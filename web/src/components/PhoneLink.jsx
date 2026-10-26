import { useEffect, useState } from "react";
import qrcode from "qrcode-generator";
import { api } from "../api.js";
import { Icon, Sheet } from "./ui.jsx";

// Indirizzo da aprire sul telefono, con QR code da inquadrare con la fotocamera.
export default function PhoneLink() {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");

  useEffect(() => {
    if (open) api.info().then((i) => setUrl(i.lan_url)).catch(() => setUrl(""));
  }, [open]);

  const svg = url
    ? (() => {
        const qr = qrcode(0, "M");
        qr.addData(url);
        qr.make();
        return qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
      })()
    : "";

  return (
    <>
      <button className="icon-btn" onClick={() => setOpen(true)} title="Apri sul telefono">
        <Icon name="phone" />
      </button>
      {open && (
        <Sheet title="Apri sul telefono" onClose={() => setOpen(false)}>
          <div className="phone-link">
            {url ? (
              <>
                <div className="qr" dangerouslySetInnerHTML={{ __html: svg }} />
                <p className="mono">{url}</p>
                <p className="small muted center">
                  Inquadra il codice con la fotocamera del telefono, collegato allo stesso Wi-Fi del PC. L'indirizzo
                  cambia se cambi rete.
                </p>
              </>
            ) : (
              <p className="muted">Indirizzo non disponibile.</p>
            )}
          </div>
        </Sheet>
      )}
    </>
  );
}
