import DawnExperience from '@/components/DawnExperience';

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-10 text-slate-100 sm:px-6 lg:px-10">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-amber-500/10 via-pink-500/5 to-transparent blur-2xl" />
      <div className="mx-auto w-full max-w-7xl">
        <DawnExperience />
      </div>
    </main>
  );
}
