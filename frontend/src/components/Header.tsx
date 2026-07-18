export default function Header() {
  return (
    <header className="flex h-16 shrink-0 items-center gap-x-4 border-b border-[#273647] bg-[#051424] px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:px-8">
      <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
        <div className="relative flex flex-1 items-center">
          <h1 className="text-lg font-semibold leading-6 text-[#d4e4fa]">Acme Corp</h1>
        </div>
      </div>
    </header>
  );
}
