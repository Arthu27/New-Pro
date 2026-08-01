"""
Имяvanced Reporting & Analytics
Geliшmiш raporlama ve analitik sistemi
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
import statistics


class ReportBuilder:
    """Ёzel rapor создатьucu"""
    
    def __init__(self):
        self.reports_file = 'data/custom_reports.json'
        self.reports = self._loимя_reports()
    
    def _loимя_reports(self) -> Dict[str, Any]:
        """Raporlarы yюkle"""
        if os.path.exists(self.reports_file):
            try:
                with open(self.reports_file, 'r', encoding='utf-8') as f:
                    return json.loимя(f)
            except Exception:
                pass
        
        return {}
    
    def _save_reports(self):
        """Raporlarы kaydet"""
        os.maкотrs('data', exist_ok=True)
        with open(self.reports_file, 'w', encoding='utf-8') as f:
            json.dump(self.reports, f, ensure_ascii=False, indent=2)
    
    def create_report(self, report_id: str, name: str, 
                      metrics: List[str], filters: Dict[str, Any],
                      schedule: Optional[str] = None) -> Dict[str, Any]:
        """Ёzel rapor создать"""
        self.reports[report_id] = {
            'name': name,
            'metrics': metrics,
            'filters': filters,
            'schedule': schedule,
            'created_at': datetime.now().isoformat(),
            'last_generated': None
        }
        
        self._save_reports()
        
        return self.reports[report_id]
    
    def generate_report(self, report_id: str, start_date: datetime, 
                       end_date: datetime) -> Dict[str, Any]:
        """Rapor создать"""
        if report_id not in self.reports:
            return {'error': 'Rapor не найден'}
        
        report_config = self.reports[report_id]
        
        # Verileri topla
        data = self._collect_data(report_config['metrics'], 
                                  report_config['filters'],
                                  start_date, end_date)
        
        # Rapor создать
        report = {
            'report_id': report_id,
            'name': report_config['name'],
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'generated_at': datetime.now().isoformat(),
            'data': data
        }
        
        # Son создатьma zamanыnы деньcelle
        self.reports[report_id]['last_generated'] = datetime.now().isoformat()
        self._save_reports()
        
        return report
    
    def _collect_data(self, metrics: List[str], filters: Dict[str, Any],
                     start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Verileri topla"""
        data = {}
        
        # Ticket verilerini yюkle
        tickets = self._loимя_tickets(start_date, end_date, filters)
        
        for metric in metrics:
            if metric == 'total_tickets':
                data[metric] = len(tickets)
            
            elif metric == 'tickets_by_status':
                data[metric] = Counter(t.get('status', 'unknown') for t in tickets)
            
            elif metric == 'tickets_by_category':
                data[metric] = Counter(t.get('category', 'unknown') for t in tickets)
            
            elif metric == 'tickets_by_priority':
                data[metric] = Counter(t.get('priority', 'medium') for t in tickets)
            
            elif metric == 'avg_resolution_time':
                resolution_times = [
                    self._calculate_resolution_time(t)
                    for t in tickets
                    if t.get('status') == 'closed'
                ]
                data[metric] = statistics.mean(resolution_times) if resolution_times else 0
            
            elif metric == 'tickets_by_day':
                data[metric] = self._group_by_day(tickets)
            
            elif metric == 'tickets_by_hour':
                data[metric] = self._group_by_hour(tickets)
            
            elif metric == 'top_categories':
                data[metric] = Counter(t.get('category', 'unknown') for t in tickets).most_common(5)
        
        return data
    
    def _loимя_tickets(self, start_date: datetime, end_date: datetime,
                     filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Ticket'larы yюkle"""
        tickets_file = 'data/customer_tickets.json'
        
        if not os.path.exists(tickets_file):
            return []
        
        try:
            with open(tickets_file, 'r', encoding='utf-8') as f:
                tickets = json.loимя(f)
        except Exception:
            return []
        
        # Tarih filtresi
        filtered = []
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if not created_at:
                continue
            
            ticket_date = datetime.fromisoformat(created_at)
            if start_date <= ticket_date <= end_date:
                # Другой filtreleri uygula
                if self._apply_filters(ticket, filters):
                    filtered.append(ticket)
        
        return filtered
    
    def _apply_filters(self, ticket: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Filtreleri uygula"""
        for key, value in filters.items():
            if key == 'status' and ticket.get('status') != value:
                return False
            elif key == 'category' and ticket.get('category') != value:
                return False
            elif key == 'priority' and ticket.get('priority') != value:
                return False
        
        return True
    
    def _calculate_resolution_time(self, ticket: Dict[str, Any]) -> float:
        """Чёzюm длительностьni hesapla (saat)"""
        created_at = ticket.get('created_at')
        closed_at = ticket.get('closed_at')
        
        if not created_at or not closed_at:
            return 0
        
        created = datetime.fromisoformat(created_at)
        closed = datetime.fromisoformat(closed_at)
        
        return (closed - created).total_seconds() / 3600
    
    def _group_by_day(self, tickets: List[Dict[str, Any]]) -> Dict[str, int]:
        """Деньlere gёre grupla"""
        by_day = defaultdict(int)
        
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                day = datetime.fromisoformat(created_at).strftime('%Y-%m-%d')
                by_day[day] += 1
        
        return dict(by_day)
    
    def _group_by_hour(self, tickets: List[Dict[str, Any]]) -> Dict[int, int]:
        """Saatlere gёre grupla"""
        by_hour = defaultdict(int)
        
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                hour = datetime.fromisoformat(created_at).hour
                by_hour[hour] += 1
        
        return dict(by_hour)
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Raporu al"""
        return self.reports.get(report_id)
    
    def delete_report(self, report_id: str) -> bool:
        """Raporu удалить"""
        if report_id in self.reports:
            del self.reports[report_id]
            self._save_reports()
            return True
        return False
    
    def list_reports(self) -> List[Dict[str, Any]]:
        """Все raporlarы listele"""
        return [
            {
                'report_id': report_id,
                'name': report['name'],
                'metrics': report['metrics'],
                'schedule': report.get('schedule'),
                'created_at': report['created_at'],
                'last_generated': report.get('last_generated')
            }
            for report_id, report in self.reports.items()
        ]


class AnalyticsEngine:
    """Analitik motoru"""
    
    def __init__(self):
        self.tickets_file = 'data/customer_tickets.json'
    
    def get_overview(self, days: int = 30) -> Dict[str, Any]:
        """Genel bakыш"""
        start_date = datetime.now() - timedelta(days=days)
        tickets = self._loимя_tickets_since(start_date)
        
        total = len(tickets)
        open_tickets = sum(1 for t in tickets if t.get('status') == 'open')
        closed_tickets = sum(1 for t in tickets if t.get('status') == 'closed')
        
        # Чёzюm длительность
        resolution_times = [
            self._calculate_resolution_time(t)
            for t in tickets
            if t.get('status') == 'closed'
        ]
        
        avg_resolution = statistics.mean(resolution_times) if resolution_times else 0
        
        # Kategoriler
        categories = Counter(t.get('category', 'unknown') for t in tickets)
        
        # Ёncelikler
        priorities = Counter(t.get('priority', 'medium') for t in tickets)
        
        return {
            'total_tickets': total,
            'open_tickets': open_tickets,
            'closed_tickets': closed_tickets,
            'avg_resolution_time': round(avg_resolution, 2),
            'categories': dict(categories),
            'priorities': dict(priorities),
            'period_days': days
        }
    
    def get_trends(self, days: int = 30) -> Dict[str, Any]:
        """Trendleri al"""
        start_date = datetime.now() - timedelta(days=days)
        tickets = self._loимя_tickets_since(start_date)
        
        # Ежедневный trend
        by_day = defaultdict(int)
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                day = datetime.fromisoformat(created_at).strftime('%Y-%m-%d')
                by_day[day] += 1
        
        # Saatlik trend
        by_hour = defaultdict(int)
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                hour = datetime.fromisoformat(created_at).hour
                by_hour[hour] += 1
        
        return {
            'by_day': dict(sorted(by_day.items())),
            'by_hour': dict(sorted(by_hour.items()))
        }
    
    def get_performance_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Performans metrikleri"""
        start_date = datetime.now() - timedelta(days=days)
        tickets = self._loимя_tickets_since(start_date)
        
        closed_tickets = [t for t in tickets if t.get('status') == 'closed']
        
        if not closed_tickets:
            return {
                'avg_resolution_time': 0,
                'median_resolution_time': 0,
                'fastest_resolution': 0,
                'slowest_resolution': 0,
                'resolution_rate': 0
            }
        
        resolution_times = [
            self._calculate_resolution_time(t)
            for t in closed_tickets
        ]
        
        return {
            'avg_resolution_time': round(statistics.mean(resolution_times), 2),
            'median_resolution_time': round(statistics.median(resolution_times), 2),
            'fastest_resolution': round(min(resolution_times), 2),
            'slowest_resolution': round(max(resolution_times), 2),
            'resolution_rate': round(len(closed_tickets) / len(tickets) * 100, 2) if tickets else 0
        }
    
    def _loимя_tickets_since(self, start_date: datetime) -> List[Dict[str, Any]]:
        """Belirli tarihten itibaren ticket'larы yюkle"""
        if not os.path.exists(self.tickets_file):
            return []
        
        try:
            with open(self.tickets_file, 'r', encoding='utf-8') as f:
                tickets = json.loимя(f)
        except Exception:
            return []
        
        filtered = []
        for ticket in tickets:
            created_at = ticket.get('created_at')
            if created_at:
                ticket_date = datetime.fromisoformat(created_at)
                if ticket_date >= start_date:
                    filtered.append(ticket)
        
        return filtered
    
    def _calculate_resolution_time(self, ticket: Dict[str, Any]) -> float:
        """Чёzюm длительностьni hesapla (saat)"""
        created_at = ticket.get('created_at')
        closed_at = ticket.get('closed_at')
        
        if not created_at or not closed_at:
            return 0
        
        created = datetime.fromisoformat(created_at)
        closed = datetime.fromisoformat(closed_at)
        
        return (closed - created).total_seconds() / 3600


class ReportExporter:
    """Rapor dышa aktarыcы"""
    
    def export_to_json(self, report: Dict[str, Any], filepath: str) -> bool:
        """JSON olarak dышa aktar"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def export_to_csv(self, report: Dict[str, Any], filepath: str) -> bool:
        """CSV olarak dышa aktar"""
        try:
            import csv
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Заголовок
                writer.writerow(['Metric', 'Value'])
                
                # Veriler
                for key, value in report.get('data', {}).items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            writer.writerow([f"{key}.{sub_key}", sub_value])
                    elif isinstance(value, list):
                        for item in value:
                            writer.writerow([key, item])
                    else:
                        writer.writerow([key, value])
            
            return True
        except Exception:
            return False
    
    def export_to_html(self, report: Dict[str, Any], filepath: str) -> bool:
        """HTML olarak dышa aktar"""
        try:
            html = f"""
<!DOCTYPE html>
<html>
<heимя>
    <meta charset="UTF-8">
    <title>{report.get('name', 'Report')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .metric {{ margin: 10px 0; }}
        .metric-label {{ font-weight: bold; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; pимяding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</heимя>
<body>
    <h1>{report.get('name', 'Report')}</h1>
    <p>Period: {report.get('period', {}).get('start', 'N/A')} - {report.get('period', {}).get('end', 'N/A')}</p>
    <p>Generated: {report.get('generated_at', 'N/A')}</p>
    
    <h2>Data</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Value</th>
        </tr>
"""
            
            for key, value in report.get('data', {}).items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        html += f"        <tr><td>{key}.{sub_key}</td><td>{sub_value}</td></tr>\n"
                elif isinstance(value, list):
                    for item in value:
                        html += f"        <tr><td>{key}</td><td>{item}</td></tr>\n"
                else:
                    html += f"        <tr><td>{key}</td><td>{value}</td></tr>\n"
            
            html += """
    </table>
</body>
</html>
"""
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            return True
        except Exception:
            return False


# Global instances
report_builder = ReportBuilder()
analytics_engine = AnalyticsEngine()
report_exporter = ReportExporter()
