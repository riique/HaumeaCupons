function Header() {
  return (
    <header className="border-b border-gray-100">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-6 sm:px-8 lg:px-10">
        <h1 className="text-xl font-light tracking-normal text-ink sm:text-2xl">HaumeaCupons</h1>
        <div className="flex items-center gap-2 text-sm font-light text-slate-500">
          <span className="h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
          <span>Bot ativo</span>
        </div>
      </div>
    </header>
  )
}

export default Header
