import { useState } from "react";
import { Languages, Menu, X } from "lucide-react";
import { Link, NavLink, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { useLogout, useMe } from "@/features/auth/hooks";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "./nav";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-control px-3 py-2 text-sm font-bold transition-colors duration-200",
    isActive
      ? "bg-white/10 text-heading"
      : "text-body hover:bg-white/5 hover:text-heading",
  );

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const me = useMe();
  const logout = useLogout();

  function onLogout() {
    logout.mutate(undefined, { onSuccess: () => void navigate("/login", { replace: true }) });
  }

  const actions = (
    <>
      {me.data?.is_staff && (
        <Button asChild variant="secondary">
          <a href="/admin/">Admin</a>
        </Button>
      )}
      <Button variant="ghost" onClick={onLogout} disabled={logout.isPending}>
        Logout
      </Button>
    </>
  );

  return (
    <header className="border-b border-card-border bg-chrome">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link
          to="/"
          className="flex items-center gap-2 rounded-control font-heading text-lg font-extrabold text-heading"
        >
          <Languages className="size-6 text-purple" aria-hidden="true" />
          Frenchia
        </Link>

        <nav aria-label="Primary" className="ml-4 hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-2 md:flex">{actions}</div>

        <button
          type="button"
          className="ml-auto cursor-pointer rounded-control p-2 text-heading md:hidden"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? <X className="size-6" aria-hidden="true" /> : <Menu className="size-6" aria-hidden="true" />}
        </button>
      </div>

      {menuOpen && (
        <div id="mobile-menu" className="border-t border-card-border px-4 pb-4 md:hidden">
          <nav aria-label="Primary mobile" className="flex flex-col gap-1 py-3">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={linkClass}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">{actions}</div>
        </div>
      )}
    </header>
  );
}
