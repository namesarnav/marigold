import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer style={{ backgroundColor: "#282828" }} className="px-6 md:px-12 py-12">
      <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-10">
        {/* Col 1: Logo + tagline */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="h-7 w-7 rounded-lg bg-fl-yellow flex items-center justify-center text-fl-black text-xs font-bold font-sans">M</div>
            <span className="font-serif text-lg text-cream">Marigold</span>
          </div>
          <p className="text-sm font-sans text-cream/50 leading-relaxed">Study smarter, not longer.</p>
        </div>

        {/* Col 2: Product */}
        <div>
          <p className="text-xs font-sans font-semibold text-cream/40 uppercase tracking-wider mb-4">Product</p>
          <div className="flex flex-col gap-2">
            <Link to="/" className="text-sm font-sans text-cream/70 hover:text-cream transition-colors">Home</Link>
            <Link to="/pricing" className="text-sm font-sans text-cream/70 hover:text-cream transition-colors">Pricing</Link>
            <Link to="/dashboard" className="text-sm font-sans text-cream/70 hover:text-cream transition-colors">Dashboard</Link>
          </div>
        </div>

        {/* Col 3: Company */}
        <div>
          <p className="text-xs font-sans font-semibold text-cream/40 uppercase tracking-wider mb-4">Company</p>
          <div className="flex flex-col gap-2">
            <span className="text-sm font-sans text-cream/40">About</span>
            <span className="text-sm font-sans text-cream/40">Contact</span>
            <span className="text-sm font-sans text-cream/40">Privacy</span>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto mt-10 pt-6 border-t border-cream/10">
        <p className="text-xs font-sans text-cream/30">© {new Date().getFullYear()} Marigold. All rights reserved.</p>
      </div>
    </footer>
  );
}
