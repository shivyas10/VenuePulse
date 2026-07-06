import { useEffect, useState } from "react";
import { api } from "./api/client";
import Dashboard from "./components/Dashboard";
import LoginPage from "./components/LoginPage";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; username: string };

function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    (async () => {
      // Django's CSRF middleware requires a token even on the login
      // request itself, so grab the cookie before attempting anything.
      await api.bootstrapCsrf().catch(() => undefined);
      try {
        const session = await api.session();
        setAuth({ status: "authenticated", username: session.username });
      } catch {
        setAuth({ status: "anonymous" });
      }
    })();
  }, []);

  if (auth.status === "loading") {
    return <div className="centered-message">Loading...</div>;
  }

  if (auth.status === "anonymous") {
    return <LoginPage onLoggedIn={(username) => setAuth({ status: "authenticated", username })} />;
  }

  return <Dashboard username={auth.username} onLoggedOut={() => setAuth({ status: "anonymous" })} />;
}

export default App;
