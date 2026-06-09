import { Card } from '@shared'
export default function HomeScreen() {
  return (
    <div className="p-5">
      <Card padding="lg" shadow="sm">
        <h1 className="text-xl font-bold text-ink-primary">Home</h1>
        <p className="text-sm text-ink-tertiary mt-1">Coming in F-7+</p>
      </Card>
    </div>
  )
}
