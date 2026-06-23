import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import api from '../lib/axios'

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; in_stock: boolean | null; image_path: string | null
}

const kes = (v: string) =>
  `KSh ${parseFloat(v).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`

export default function CustomerMenuScreen() {
  const navigate = useNavigate()
  const { tabId } = useParams<{ tabId: string }>()

  const { data: items = [], isLoading } = useQuery<MenuItem[]>({
    queryKey: ['menu-items-customer'],
    queryFn: () => api.get<MenuItem[]>('/menu/items').then(r => r.data),
    staleTime: 5 * 60_000,
    select: all => all.filter(i => i.prep_station === 'KITCHEN' || i.prep_station === 'BAR'),
  })

  const grouped = useMemo(() =>
    items.reduce<Record<string, MenuItem[]>>((acc, item) => {
      const cat = item.category ?? 'Other'
      ;(acc[cat] ??= []).push(item)
      return acc
    }, {})
  , [items])

  return (
    <div className="min-h-screen p-6 md:p-10">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="font-serif text-4xl md:text-5xl font-bold text-[#f9dcd5] tracking-tight">
            Our Menu
          </h1>
          <p className="text-ink-tertiary mt-2">Waterfront Country Club</p>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="grid grid-cols-2 md:grid-cols-[2fr_1fr_1fr] gap-4">
            {[1,2,3,4,5,6].map(i => (
              <div key={i} className="h-40 rounded-2xl animate-pulse glass-card" />
            ))}
          </div>
        )}

        {/* Categories */}
        {Object.entries(grouped).map(([category, catItems]) => (
          <div key={category} className="mb-10">
            <h2 className="font-serif text-xl font-bold text-[#f9dcd5]/80 mb-4 border-b border-white/10 pb-2">
              {category}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-[2fr_1fr_1fr] gap-4">
              {catItems.map(item => {
                const soldOut = item.in_stock === false
                return (
                  <motion.div key={item.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`glass-card overflow-hidden ${soldOut ? 'opacity-40' : ''}`}>

                    {/* Photo */}
                    <div className="h-28 bg-gradient-to-br from-white/5 to-transparent flex items-center justify-center">
                      {item.image_path ? (
                        <img src={item.image_path} alt={item.name} className="w-full h-full object-cover" />
                      ) : (
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" className="opacity-20 text-ink-tertiary">
                          <path d="M3 6l3 6v8M8 6c0 3-1.5 5-3 6M12 3v18M16 6c0 3 1.5 5 3 6M21 6l-3 6v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      )}
                      {soldOut && (
                        <div className="absolute inset-0 flex items-center justify-center bg-[rgba(30,16,12,0.6)]">
                          <span className="text-xs font-bold text-[#f9dcd5]/70 uppercase">Sold Out</span>
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="p-4">
                      <p className="text-sm font-semibold text-[#f9dcd5]">{item.name}</p>
                      <p className="text-sm tabular-nums text-[#fa5c29] font-bold mt-1">
                        {soldOut ? '—' : kes(item.price)}
                      </p>
                    </div>
                  </motion.div>
                )
              })}
            </div>
          </div>
        ))}

        {/* Open to Order button */}
        <div className="text-center mt-8">
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={() => navigate(tabId ? `/pos/tabs/${tabId}` : '/pos/tabs')}
            className="px-8 py-4 rounded-2xl gradient-hero text-[#f9dcd5] font-bold text-lg
              shadow-lg hover:shadow-xl transition-shadow">
            Open to Order →
          </motion.button>
        </div>
      </div>
    </div>
  )
}
