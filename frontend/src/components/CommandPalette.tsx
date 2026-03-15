import React, { useState, useEffect } from 'react'
import { Command } from 'cmdk'
import { useHotkeys } from 'react-hotkeys-hook'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Plus, Play, Square, Trash2, RotateCcw } from 'lucide-react'
import { useStore } from '../stores/useStore';
export const CommandPalette = () => {
  const [open, setOpen] = useState(false)
  const { tickers, connected, paused } = useStore()

  // Toggle palette with Cmd+K or Ctrl+K
  useHotkeys('mod+k', (e) => {
    e.preventDefault()
    setOpen((open) => !open)
  })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] bg-black/50 backdrop-blur-sm p-4">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-[640px] bg-popover text-popover-foreground rounded-xl border shadow-2xl overflow-hidden"
      >
        <Command className="flex flex-col h-full">
          <div className="flex items-center border-b px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <Command.Input 
              placeholder="Search symbols or type a command..." 
              className="flex h-12 w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
          <Command.List className="max-h-[300px] overflow-y-auto p-2">
            <Command.Empty className="py-6 text-center text-sm">No results found.</Command.Empty>
            
            <Command.Group heading="Global Actions" className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              <Command.Item className="flex items-center gap-2 px-2 py-3 rounded-md hover:bg-accent cursor-pointer">
                <Plus className="w-4 h-4" /> Add New Ticker
              </Command.Item>
              <Command.Item className="flex items-center gap-2 px-2 py-3 rounded-md hover:bg-accent cursor-pointer">
                {paused ? <Play className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                {paused ? 'Resume Bot' : 'Pause All Trading'}
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Active Symbols" className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {Object.keys(tickers).map((symbol) => (
                <Command.Item key={symbol} className="flex items-center justify-between gap-2 px-2 py-3 rounded-md hover:bg-accent cursor-pointer">
                  <div className="flex items-center gap-2">
                    <span className="font-bold">{symbol}</span>
                  </div>
                  <div className="flex gap-4 opacity-50 text-[10px]">
                    <span className="flex items-center gap-1"><Play className="w-3 h-3"/> Place</span>
                    <span className="flex items-center gap-1"><RotateCcw className="w-3 h-3"/> Reset</span>
                    <span className="flex items-center gap-1 text-destructive"><Trash2 className="w-3 h-3"/> Delete</span>
                  </div>
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </motion.div>
    </div>
  )
}