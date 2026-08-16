import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Button, Input } from '@shared'
import api from '../lib/axios'

export default function RegisterScreen() {
  const navigate = useNavigate()
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [form, setForm] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    fullName: '',
    phone: '',
    departmentId: '',
    pin: '',
    confirmPin: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const departments = [
    { id: 'kitchen', name: 'Kitchen' },
    { id: 'bar', name: 'Bar' },
    { id: 'front-of-house', name: 'Front of House' },
    { id: 'gate', name: 'Gate / Security' },
    { id: 'villa', name: 'Villa / Housekeeping' },
    { id: 'water', name: 'Water Activities' },
    { id: 'spa', name: 'Spa & Wellness' },
    { id: 'maintenance', name: 'Maintenance' },
    { id: 'general', name: 'General' },
  ]

  async function handleSubmit() {
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (form.pin !== form.confirmPin) {
      setError('PINs do not match')
      return
    }
    if (form.pin.length !== 4) {
      setError('PIN must be exactly 4 digits')
      return
    }

    setLoading(true)
    setError('')
    try {
      await api.post('/auth/register', {
        username: form.username.trim().toLowerCase(),
        password: form.password,
        full_name: form.fullName.trim(),
        phone: form.phone.trim(),
        department_id: form.departmentId,
        pin: form.pin,
      })
      setStep(3)
    } catch (e: any) {
      setError(e?.response?.data?.error || 'Registration failed. Try a different username.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4"
      style={{ background: 'linear-gradient(160deg, rgba(35,18,12,0.9) 0%, rgba(18,9,6,0.7) 100%)' }}>
      
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md glass-card p-6 md:p-8"
      >
        {/* Header */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Join Kurahia</h1>
          <p className="text-sm text-ink-tertiary mt-1">Create your staff account</p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {[1, 2, 3].map(s => (
            <div key={s} className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${s === step ? 'bg-primary-main text-white' : s < step ? 'bg-primary-main/30 text-primary-light' : 'bg-white/10 text-ink-tertiary'}`}>
              {s < step ? '✓' : s}
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-status-failed/15 border border-status-failed/25 text-status-failed text-sm">
            {error}
          </div>
        )}

        {/* STEP 1: Account basics */}
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Username</label>
              <Input
                value={form.username}
                onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                placeholder="e.g. mwangi_kitchen"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Full Name</label>
              <Input
                value={form.fullName}
                onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))}
                placeholder="Your full name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Phone Number</label>
              <Input
                value={form.phone}
                onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                placeholder="e.g. +254 712 345 678"
                type="tel"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Department</label>
              <select
                value={form.departmentId}
                onChange={e => setForm(f => ({ ...f, departmentId: e.target.value }))}
                className="w-full px-4 py-3 rounded-xl bg-white/[0.06] border border-white/15 text-ink-primary
                  focus:border-primary-main focus:outline-none"
              >
                <option value="" disabled>Select your department</option>
                {departments.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <Button onClick={() => {
              if (!form.username || !form.fullName || !form.phone || !form.departmentId) {
                setError('Please fill in all fields')
                return
              }
              setError(''); setStep(2)
            }} className="w-full">
              Next: Set Password
            </Button>
          </div>
        )}

        {/* STEP 2: Password + PIN */}
        {step === 2 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Password</label>
              <Input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="Min 6 characters"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Confirm Password</label>
              <Input
                type="password"
                value={form.confirmPassword}
                onChange={e => setForm(f => ({ ...f, confirmPassword: e.target.value }))}
                placeholder="Repeat password"
              />
            </div>
            
            <div className="border-t border-white/10 pt-4">
              <label className="block text-sm font-medium text-ink-secondary mb-1">4-Digit PIN (for quick login)</label>
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                value={form.pin}
                onChange={e => setForm(f => ({ ...f, pin: e.target.value.replace(/\\D/g, '') }))}
                placeholder="1234"
              />
              <p className="text-xs text-ink-tertiary mt-1">You'll use this PIN to log in quickly on your phone</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1">Confirm PIN</label>
              <Input
                type="password"
                inputMode="numeric"
                maxLength={4}
                value={form.confirmPin}
                onChange={e => setForm(f => ({ ...f, confirmPin: e.target.value.replace(/\\D/g, '') }))}
                placeholder="1234"
              />
            </div>

            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => setStep(1)} className="flex-1">Back</Button>
              <Button onClick={handleSubmit} loading={loading} className="flex-1">Create Account</Button>
            </div>
          </div>
        )}

        {/* STEP 3: Success */}
        {step === 3 && (
          <div className="text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-status-paid/15 border border-status-paid/25
              flex items-center justify-center mx-auto">
              <span className="text-3xl">🎉</span>
            </div>
            <h2 className="text-xl font-bold text-ink-primary">Account Created!</h2>
            <p className="text-sm text-ink-secondary">
              Your manager will review and activate your account. You'll receive a notification when approved.
            </p>
            <Button onClick={() => navigate('/login')} className="w-full">Go to Login</Button>
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-xs text-ink-tertiary">
            Already have an account?{' '}
            <button onClick={() => navigate('/login')} className="text-primary-main hover:underline">
              Log in
            </button>
          </p>
        </div>
      </motion.div>
    </div>
  )
}
