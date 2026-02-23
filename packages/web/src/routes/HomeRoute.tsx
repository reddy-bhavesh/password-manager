import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuthStore } from "../features/auth/store";

export function HomeRoute() {
  const navigate = useNavigate();
  const accessToken = useAuthStore((state) => state.accessToken);

  useEffect(() => {
    void navigate({ to: accessToken ? "/vault" : "/login", replace: true });
  }, [accessToken, navigate]);

  return <p className="route-loading">Redirecting...</p>;
}
