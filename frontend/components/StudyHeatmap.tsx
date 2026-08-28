import { faNumber } from "@/lib/fa";

type HeatmapDay = { date: string; count: number };

export default function StudyHeatmap({ days }: { days: HeatmapDay[] }) {
  const max = Math.max(1, ...days.map(day => day.count));
  return (
    <div className="study-heatmap" aria-label="نقشه فعالیت ۴۲ روز اخیر">
      {days.map(day => {
        const level = day.count === 0 ? 0 : Math.max(1, Math.ceil(day.count * 4 / max));
        return (
          <div
            key={day.date}
            className={`heat-cell level-${level}`}
            title={`${day.date}: ${day.count} فعالیت`}
            aria-label={`${day.date}: ${faNumber(day.count)} فعالیت`}
          />
        );
      })}
    </div>
  );
}
