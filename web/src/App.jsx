import { useEffect, useState } from "react";
import { api } from "./api.js";
import RecordingList from "./components/RecordingList.jsx";
import Detail from "./components/Detail.jsx";
import Login from "./components/Login.jsx";
import Templates from "./components/Templates.jsx";

// Navigazione con l'hash (#/r/<id>): funziona senza configurazioni sul server e con il tasto indietro.
function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const parts = hash.replace(/^#\/?/, "").split("/");
  return { page: parts[0] || "list", id: parts[1] };
}

export default function App() {
  const route = useRoute();
  const [auth, setAuth] = useState("checking");

  useEffect(() => {
    api
      .session()
      .then((s) => setAuth(s.authenticated ? "ok" : "login"))
      .catch(() => setAuth("ok")); // se il server non risponde, l'errore compare nella pagina
    const onAuth = () => setAuth("login");
    window.addEventListener("auth-required", onAuth);
    return () => window.removeEventListener("auth-required", onAuth);
  }, []);

  if (auth === "checking") return null;
  if (auth === "login") return <Login onDone={() => setAuth("ok")} />;
  if (route.page === "r" && route.id) return <Detail id={route.id} key={route.id} />;
  if (route.page === "template") return <Templates />;
  return <RecordingList />;
}
