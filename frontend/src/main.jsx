import React, { useEffect, useMemo, useState } from 'react';
import { BarChart3, CircleAlert, FileText, Gauge, LoaderCircle, Search, Star, Target, TrendingUp } from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const api = async (path, options) => {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail?.message || body.detail || body.error || 'The request could not be completed.');
  return body;
};

const formatScore = (value) => `${value >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}`;
const short = (value, length = 30) => String(value || '').length > length ? `${String(value).slice(0, length - 1)}...` : String(value || '');
const sentimentClass = (value) => value >= 0.2 ? 'positive' : value <= -0.2 ? 'negative' : 'neutral';
const normalizeTopicLabel = (label) => {
  const value = String(label || '').toLowerCase();
  if (/shipping|shipped|arrived|delivery|quickly|fast/.test(value)) return 'Shipping and delivery';
  if (/fit|fits|size|sizing|tie|ties|comfortable/.test(value)) return 'Fit and sizing';
  if (/quality|fabric|material|cotton|sturdy|workmanship/.test(value)) return 'Product quality';
  if (/color|colour|pictured|appearance|design/.test(value)) return 'Color and appearance';
  if (/gift|daughter|friend/.test(value)) return 'Gifting';
  if (/apron|smock/.test(value)) return 'Apron experience';
  if (/purchase|bought|order|ordering/.test(value)) return 'Purchase experience';
  return String(label || 'Customer experience').replace(/\s*\/\s*.*/, '').replace(/\b\w/g, (letter) => letter.toUpperCase());
};

function App() {
  const [reports, setReports] = useState([]);
  const [report, setReport] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [page, setPage] = useState('research');

  useEffect(() => {
    api('/api/reports').then((data) => {
      setReports(data.reports || []);
    }).catch((error) => setMessage(error.message));
  }, []);

  const loadReport = async (filename) => {
    try { setReport(await api(`/api/reports/${encodeURIComponent(filename)}`)); setMessage(''); }
    catch (error) { setMessage(error.message); }
  };

  const analyze = async (event) => {
    event.preventDefault();
    const listingIds = input.split(/[\n,]+/).map((value) => value.trim()).filter(Boolean);
    if (!listingIds.length || listingIds.length > 10) { setMessage('Enter between one and ten Etsy listing IDs or URLs.'); return; }
    setLoading(true); setMessage('');
    try {
      const result = await api('/api/analyze', { method: 'POST', body: JSON.stringify({ listing_ids: listingIds }) });
      setReport(result);
      setReports((current) => [result.saved_file, ...current.filter((item) => item !== result.saved_file)]);
      setInput('');
      setPage('dashboard');
    } catch (error) { setMessage(error.message); }
    finally { setLoading(false); }
  };

  const goToResearch = () => { setPage('research'); setMessage(''); };

  const comparison = report?.comparison;
  const kpi = report?.sentiment_analysis;
  return (
    <div className="app-shell">
      <main className={page === 'dashboard' ? 'dashboard-main' : ''}>
        {page === 'research' && !loading && (
          <section className="hero">
            <div className="hero-content">
              <h1>Turn every Etsy review into your next best-selling decision.</h1>
              <form onSubmit={analyze} className="analyze-form">
                <div className="input-wrap">
                  {loading ? <LoaderCircle className="spin" size={19} /> : <Search size={19} />}
                  <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }} placeholder="Paste Etsy listing IDs or URLs (ex: 1042603482)" aria-label="Etsy listing IDs or URLs" disabled={loading} />
                </div>
              </form>
            </div>
          </section>
        )}
        {loading && <AnalysisLoading />}
        {message && <div className="alert"><CircleAlert size={17} /> {message}</div>}
        {page === 'dashboard' && (
          <DashboardView
            report={report}
            comparison={comparison}
            kpi={kpi}
            reports={reports}
            loadReport={loadReport}
            onResearch={goToResearch}
          />
        )}
      </main>
      <footer className="site-signature">Better feedback. Stronger Etsy sales.</footer>
    </div>
  );
}

function AnalysisLoading() {
  return <section className="analysis-loading" aria-live="polite" aria-label="Analysing Etsy reviews"><div className="loading-orbit"><i /><i /><i /></div><div className="loading-copy"><h1>Finding the story behind your reviews</h1><p>Collecting feedback, analysing sentiment, and discovering customer themes.</p></div></section>;
}

function DashboardView({ report, comparison, kpi, reports, loadReport, onResearch }) {
  if (!report) {
    return (
      <div className="report-layout">
        <SubNav reports={reports} report={report} loadReport={loadReport} onResearch={onResearch} />
        <div className="report-content"><EmptyState onResearch={onResearch} /></div>
      </div>
    );
  }
  return comparison
    ? <ComparisonView comparison={comparison} report={report} reports={reports} loadReport={loadReport} onResearch={onResearch} />
    : <SingleView report={report} kpi={kpi} reports={reports} loadReport={loadReport} onResearch={onResearch} />;
}

function EmptyState({ onResearch }) {
  return <section className="empty-state"><Gauge size={30} /><h2>No report on the dashboard</h2><p>Select a saved report or start a new research query.</p>{onResearch && <button type="button" className="research-back-btn" onClick={onResearch}><Search size={16} /> New research</button>}</section>;
}

function SubNav({ onResearch }) {
  return <aside className="sub-nav" aria-label="Report navigation"><button type="button" className="research-back" onClick={onResearch} aria-label="Back to research"><Search size={18} /></button><div className="wordmark"><span className="mark" />Review Intelligence</div><nav className="section-links"><a href="#overview">Overview</a><a href="#sentiment">Sentiment</a><a href="#topics">Topics</a><a href="#trends">Trends</a></nav></aside>;
}

function ReportLayout({ children, reports, report, loadReport, onResearch }) { return <div className="report-layout"><SubNav reports={reports} report={report} loadReport={loadReport} onResearch={onResearch} /><div className="report-content">{children}</div></div>; }

function KpiCard({ icon: Icon, label, value, detail, tone = '' }) {
  return <article className="kpi-card"><div className="kpi-label"><Icon size={15} /> {label}</div><div className={`kpi-value ${tone}`}>{value}</div><div className="kpi-detail">{detail}</div></article>;
}

function SingleView({ report, kpi, reports, loadReport, onResearch }) {
  const scoredReviews = (report.reviews || []).filter((review) => Number.isFinite(Number(review.sentiment?.score)));
  const sentimentReliability = scoredReviews.length ? Math.round(scoredReviews.reduce((sum, review) => sum + Math.abs(Number(review.sentiment.score)), 0) / scoredReviews.length * 100) : null;
  return <ReportLayout reports={reports} report={report} loadReport={loadReport} onResearch={onResearch}>
    <section id="overview"><div className="section-heading"><div><p className="eyebrow">Single listing report</p><h2>{report.listing_title || `Listing ${report.listing_id}`}</h2></div></div>
    <section className="kpi-grid">
      <KpiCard icon={FileText} label="Reviews" value={kpi?.total_reviews ?? '-'} detail="Customer responses" />
      <KpiCard icon={Star} label="Average rating" value={kpi?.average_star_rating ? `${kpi.average_star_rating}/5` : '-'} detail="Star rating signal" tone="amber" />
      <KpiCard icon={TrendingUp} label="Positive sentiment" value={`${kpi?.positive_sentiment_percent ?? 0}%`} detail="Text classified positive" tone="green" />
      <KpiCard icon={BarChart3} label="Sentiment reliability" value={sentimentReliability == null ? '-' : `${sentimentReliability}%`} detail="Average model confidence" tone="teal" />
    </section>
    <CollectedReviews reviews={report.reviews || []} />
    </section>
    <section id="sentiment" className="sentiment-section">
    <div className="analysis-grid">
      <Panel title="Reviews by sentiment" subtitle="Volume of reviews in each sentiment class."><SentimentVolume kpi={kpi} /></Panel>
      <Panel title="Rating vs. sentiment" subtitle="Each dot is a review; disagreements are the most useful opportunities to investigate."><RatingSentimentScatter reviews={report.reviews || []} /></Panel>
    </div>
    </section>
    <section id="topics" className="topics-section">
    <div className="analysis-grid">
      <Panel title="Recurring topics & negative-review concentration" subtitle="Total topic volume is sentiment-coloured; the red overlay shows how many reviews in that topic are negative."><TopicRiskPlot topics={kpi?.review_clusters || []} /></Panel>
      <Panel title="Frequent customer language" subtitle="Words and phrases appearing most often in customer feedback."><PhraseList phrases={kpi?.key_phrases || []} /></Panel>
    </div>
    <Panel title="Intertopic distance map" subtitle="A compact view of how review topics relate to each other."><TopicMap map={kpi?.intertopic_map} /></Panel>
    </section>
    <section id="trends">
    <div className="trend-stack">
      <Panel title="Sentiment over time" subtitle="Average review sentiment by date, from -1 negative to +1 positive."><SentimentTrend trend={kpi?.sentiment_trend || []} /></Panel>
      <Panel title="Topic trend over time" subtitle="How recurring topic volume changes across review dates."><TopicTrend topics={kpi?.review_clusters || []} /></Panel>
    </div>
    </section>
  </ReportLayout>;
}

function CollectedReviews({ reviews }) {
  const visible = [...reviews].sort((a, b) => Number(b.review_date || 0) - Number(a.review_date || 0));
  if (!visible.length) return null;
  return <aside className="collected-reviews" aria-label="Collected reviews"><div className="collected-reviews-title"><span>Collected reviews</span><b>{reviews.length}</b></div><div className="collected-reviews-list">{visible.map((review, index) => <div className="collected-review" key={`${review.review_date || 'review'}-${index}`}><span className="review-rating"><Star size={12} fill="currentColor" /> {review.rating || '-'}</span><p>{review.review_text || 'No written review provided.'}</p></div>)}</div></aside>;
}

function ComparisonView({ comparison, report, reports, loadReport, onResearch }) {
  const listings = comparison.listings || [];
  return <ReportLayout reports={reports} report={report} loadReport={loadReport} onResearch={onResearch}>
    <section id="overview"><div className="section-heading"><div><p className="eyebrow">Portfolio comparison</p><h2>{listings.length} Etsy listings, one clear view</h2></div><span className="source-pill">Ranked by satisfaction</span></div>
    <section className="kpi-grid">
      <KpiCard icon={BarChart3} label="Listings compared" value={listings.length} detail="Successful analyses" />
      <KpiCard icon={TrendingUp} label="Best satisfaction" value={`${listings[0]?.satisfaction_score ?? 0}/100`} detail={short(listings[0]?.listing_title, 28)} tone="green" />
      <KpiCard icon={Target} label="Portfolio average" value={`${(listings.reduce((sum, item) => sum + item.satisfaction_score, 0) / Math.max(listings.length, 1)).toFixed(1)}/100`} detail="Across selected products" tone="teal" />
      <KpiCard icon={CircleAlert} label="Needs attention" value={`${listings[listings.length - 1]?.satisfaction_score ?? 0}/100`} detail={short(listings[listings.length - 1]?.listing_title, 28)} tone="coral" />
    </section>
    </section>
    <section id="sentiment">
    <Panel title="Satisfaction ranking" subtitle="A weighted view of review sentiment and star ratings."><Ranking listings={listings} /></Panel>
    <Panel title="All listing metrics" subtitle="Compare the evidence behind every portfolio decision."><MetricsTable listings={listings} /></Panel>
    </section>
    <section id="topics">
    <div className="analysis-grid">
      <Panel title="Recurring review topics" subtitle="The strongest topics for each product."><TopicHeatmap data={comparison.topic_heatmap} /></Panel>
      <Panel title="Reviews by sentiment" subtitle="Sentiment volume across the selected products."><ComparisonSentiment listings={listings} /></Panel>
    </div>
    <Panel title="Frequent customer language" subtitle="Product-specific language, kept separate for clarity."><ProductPhrases products={comparison.product_views || []} /></Panel>
    </section>
    <section id="trends">
    {comparison.intertopic_map?.centroids?.length > 0 && <Panel title="Intertopic distance map" subtitle="Product-labelled topic relationships across the portfolio."><TopicMap map={comparison.intertopic_map} /></Panel>}
    </section>
    {report.failures?.length > 0 && <div className="alert">Some listings could not be analysed: {report.failures.map((failure) => failure.listing_reference).join(', ')}</div>}
  </ReportLayout>;
}

function Panel({ title, subtitle, children }) { return <section className="panel"><div className="panel-heading"><div><h3>{title}</h3><p>{subtitle}</p></div></div>{children}</section>; }
function Ranking({ listings }) { const max = 100; return <div className="ranking">{listings.map((item) => <div className="ranking-row" key={item.listing_id}><div className="ranking-name"><span>#{item.rank}</span>{short(item.listing_title, 38)}</div><div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(3, item.satisfaction_score / max * 100)}%` }} /></div><strong>{item.satisfaction_score}</strong></div>)}</div>; }
function TopicRiskPlot({ topics }) {
  const visible = [...topics].sort((a, b) => (b.reviews || 0) - (a.reviews || 0)).slice(0, 10);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [hoveredTopic, setHoveredTopic] = useState(null);
  const maxReviews = Math.max(1, ...visible.map((topic) => topic.reviews || 0));
  if (!visible.length) return <div className="empty-chart">No recurring topics available yet.</div>;
  const activeTopic = hoveredTopic || selectedTopic;
  const anchorFromEvent = (topic, event) => {
    const plot = event.currentTarget.closest('.topic-risk-plot').getBoundingClientRect();
    return { topic, left: Math.max(12, Math.min(88, ((event.clientX - plot.left) / plot.width) * 100)), top: ((event.currentTarget.getBoundingClientRect().top - plot.top) / plot.height) * 100 };
  };
  return <div className="topic-risk-plot">
    <div className="topic-risk-legend"><span><i className="positive" />Positive topic volume</span><span><i className="neutral" />Neutral topic volume</span><span><i className="negative" />Negative reviews</span></div>
    {visible.map((topic) => {
      const reviews = topic.reviews || 0;
      const negative = topic.sentiment_breakdown?.negative || 0;
      return <div className={`topic-risk-row ${activeTopic?.topic?.theme === topic.theme ? 'active' : ''}`} key={`${topic.cluster_id}-${topic.theme}`} title={`${topic.theme}: ${reviews} reviews, ${negative} negative`} onClick={(event) => setSelectedTopic(anchorFromEvent(topic, event))} onMouseEnter={(event) => setHoveredTopic(anchorFromEvent(topic, event))} onMouseLeave={() => setHoveredTopic(null)}>
        <div className="topic-risk-label">{short(topic.theme, 34)}</div>
        <div className="topic-risk-track"><div className={`topic-risk-total ${sentimentClass(topic.average_sentiment)}`} style={{ width: `${reviews / maxReviews * 100}%` }} /><div className="topic-risk-negative" style={{ width: `${negative / maxReviews * 100}%` }} /></div>
        <div className="topic-risk-values"><b>{reviews}</b></div>
      </div>;
    })}
    {activeTopic && <div className="topic-risk-tooltip" aria-live="polite" style={{ left: `${activeTopic.left}%`, top: `${activeTopic.top}%` }}><strong>{short(activeTopic.topic.theme, 34)}</strong><span>{activeTopic.topic.reviews || 0} total reviews</span><span><b>{activeTopic.topic.sentiment_breakdown?.negative || 0}</b> negative reviews · {formatScore(activeTopic.topic.average_sentiment)} sentiment</span></div>}
  </div>;
}
function SentimentVolume({ kpi }) {
  const values = [
    { label: 'Positive', percent: kpi?.positive_sentiment_percent || 0, count: Math.round((kpi?.positive_sentiment_percent || 0) / 100 * (kpi?.total_reviews || 0)), tone: 'positive' },
    { label: 'Neutral', percent: kpi?.neutral_sentiment_percent || 0, count: Math.round((kpi?.neutral_sentiment_percent || 0) / 100 * (kpi?.total_reviews || 0)), tone: 'neutral' },
    { label: 'Negative', percent: kpi?.negative_sentiment_percent || 0, count: Math.round((kpi?.negative_sentiment_percent || 0) / 100 * (kpi?.total_reviews || 0)), tone: 'negative' },
  ];
  const [selected, setSelected] = useState(null);
  const total = Math.max(1, values.reduce((sum, item) => sum + item.count, 0));
  const radius = 78;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const segments = values.map((item) => {
    const length = (item.count / total) * circumference;
    const segment = { ...item, length, offset };
    offset += length;
    return segment;
  });
  const active = selected == null ? null : values[selected];
  return <div className="sentiment-pie-wrap" role="img" aria-label="Reviews by sentiment pie chart">
    <svg className="sentiment-pie" viewBox="0 0 220 220">
      <g transform="rotate(-90 110 110)">
        <circle className="pie-track" cx="110" cy="110" r={radius} />
        {segments.map((item, index) => <circle className={`pie-segment ${item.tone} ${selected === index ? 'active' : ''}`} cx="110" cy="110" r={radius} strokeDasharray={`${item.length} ${circumference - item.length}`} strokeDashoffset={-item.offset} onClick={() => setSelected(index)} key={item.label}><title>{`${item.label}: ${item.percent.toFixed(1)}%, ${item.count} reviews`}</title></circle>)}
      </g>
      <text className="pie-center-title" x="110" y="104" textAnchor="middle">{active ? `${active.percent.toFixed(1)}%` : `${kpi?.total_reviews || 0}`}</text>
      <text className="pie-center-label" x="110" y="124" textAnchor="middle">{active ? active.label : 'reviews'}</text>
      {active && <text className="pie-center-count" x="110" y="141" textAnchor="middle">{active.count} reviews</text>}
    </svg>
    <div className="sentiment-legend">{values.map((item, index) => <button className={`legend-item ${selected === index ? 'selected' : ''}`} onClick={() => setSelected(index)} key={item.label}><i className={item.tone} />{item.label}<b>{item.percent.toFixed(1)}%</b></button>)}</div>
  </div>;
}
function SentimentTrend({ trend }) {
  const [selectedIndex, setSelectedIndex] = useState(null);
  const [hoveredIndex, setHoveredIndex] = useState(null);
  if (!trend.length) return <div className="empty-chart">No dated reviews available yet.</div>;
  const width = 900;
  const height = 260;
  const padding = { top: 18, right: 24, bottom: 42, left: 42 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const x = (index) => padding.left + (index / Math.max(trend.length - 1, 1)) * innerWidth;
  const y = (value) => padding.top + ((1 - Math.max(-1, Math.min(1, value)) / 1) / 2) * innerHeight;
  const points = trend.map((item, index) => `${x(index)},${y(item.average_score)}`).join(' ');
  const zeroY = y(0);
  const activeIndex = hoveredIndex ?? selectedIndex;
  const active = activeIndex == null ? null : trend[activeIndex];
  const nearestIndex = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const chartX = ((event.clientX - bounds.left) / bounds.width) * width;
    return Math.max(0, Math.min(trend.length - 1, Math.round(((chartX - padding.left) / innerWidth) * (trend.length - 1))));
  };
  const moveToNearestPoint = (event) => setHoveredIndex(nearestIndex(event));
  return <div className="trend-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="application" aria-label="Sentiment over time line chart. Click or use left and right arrow keys to inspect a date." preserveAspectRatio="none" tabIndex="0"
      onMouseMove={moveToNearestPoint} onMouseLeave={() => setHoveredIndex(null)} onClick={(event) => setSelectedIndex(nearestIndex(event))}
      onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); setSelectedIndex((current) => Math.max(0, Math.min(trend.length - 1, (current ?? 0) + (event.key === 'ArrowLeft' ? -1 : 1)))); } }}>
      <line className="trend-grid" x1={padding.left} x2={width - padding.right} y1={y(1)} y2={y(1)} />
      <line className="trend-zero" x1={padding.left} x2={width - padding.right} y1={zeroY} y2={zeroY} />
      <line className="trend-grid" x1={padding.left} x2={width - padding.right} y1={y(-1)} y2={y(-1)} />
      <polyline className="trend-line" points={points} />
      <text className="trend-axis" x="8" y={y(1) + 4}>+1</text><text className="trend-axis" x="15" y={zeroY + 4}>0</text><text className="trend-axis" x="8" y={y(-1) + 4}>-1</text>
      <text className="trend-date" x={padding.left} y={height - 12}>{trend[0].date}</text><text className="trend-date" textAnchor="end" x={width - padding.right} y={height - 12}>{trend[trend.length - 1].date}</text>
    </svg>
    {active && <div className="trend-tooltip" aria-live="polite" style={{ left: `${x(activeIndex) / width * 100}%`, top: `${y(active.average_score) / height * 100}%` }}><strong>{active.date}</strong><span>{formatScore(active.average_score)} sentiment</span><span>{active.reviews} reviews</span></div>}
  </div>;
}
function RatingSentimentScatter({ reviews }) {
  const points = reviews.filter((review) => Number(review.rating) >= 1 && review.sentiment).map((review) => ({ rating: Number(review.rating), sentiment: Number(review.sentiment.score || 0), text: review.review_text || '' }));
  const [selectedIndex, setSelectedIndex] = useState(null);
  const [hoveredIndex, setHoveredIndex] = useState(null);
  if (!points.length) return <div className="empty-chart">No rating and sentiment pairs available yet.</div>;
  const x = (rating) => 8 + ((rating - 1) / 4) * 84;
  const y = (score) => 88 - ((score + 1) / 2) * 76;
  const activeIndex = hoveredIndex ?? selectedIndex;
  const active = activeIndex == null ? null : points[activeIndex];
  return <div className="scatter-chart"><svg viewBox="0 0 900 260" preserveAspectRatio="none" role="img" aria-label="Rating versus sentiment scatter plot. Hover, click, or tab to a dot to inspect its review."><line className="trend-zero" x1="42" x2="860" y1="130" y2="130" />{points.map((point, index) => <circle className={`scatter-point ${sentimentClass(point.sentiment)} ${activeIndex === index ? 'active' : ''}`} cx={`${x(point.rating)}%`} cy={`${y(point.sentiment)}%`} r="5" key={index} role="button" tabIndex="0" aria-label={`${point.rating} stars and ${formatScore(point.sentiment)} sentiment`} onMouseEnter={() => setHoveredIndex(index)} onMouseLeave={() => setHoveredIndex(null)} onFocus={() => setSelectedIndex(index)} onClick={() => setSelectedIndex((current) => current === index ? null : index)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedIndex((current) => current === index ? null : index); } }}><title>{`${point.rating} stars, ${formatScore(point.sentiment)} sentiment`}</title></circle>)}<text className="trend-axis" x="28" y="22">+1 sentiment</text><text className="trend-axis" x="28" y="246">-1 sentiment</text><text className="trend-date" x="42" y="258">1 star</text><text className="trend-date" textAnchor="end" x="860" y="258">5 stars</text></svg>{active && <div className="scatter-tooltip" aria-live="polite" style={{ left: `${x(active.rating)}%`, top: `${y(active.sentiment)}%` }}><strong>{active.rating} stars · {formatScore(active.sentiment)}</strong>{active.text && <span>{short(active.text, 100)}</span>}</div>}</div>;
}
function TopicTrend({ topics }) {
  const dates = [...new Set(topics.flatMap((topic) => Object.keys(topic.date_counts || {})))].sort();
  const selected = topics.slice(0, 6);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [hoveredPoint, setHoveredPoint] = useState(null);
  if (!dates.length || !selected.length) return <div className="empty-chart">No dated topic data available yet.</div>;
  const max = Math.max(1, ...dates.map((date) => selected.reduce((sum, topic) => sum + (topic.date_counts?.[date] || 0), 0)));
  const activePoint = hoveredPoint || selectedPoint;
  const activeTopic = selected.find((topic) => topic.theme === (activePoint?.theme || selectedTopic));
  const activeDate = activePoint?.date;
  const pointFromEvent = (topic, date, event) => {
    const container = event.currentTarget.closest('.topic-trend');
    const segment = event.currentTarget.getBoundingClientRect();
    const bounds = container.getBoundingClientRect();
    return { theme: topic.theme, date, left: ((segment.left - bounds.left + segment.width / 2) / bounds.width) * 100, top: ((segment.top - bounds.top) / bounds.height) * 100 };
  };
  return <div className="topic-trend">
    <div className="topic-trend-legend">{selected.map((topic, index) => <button className={`topic-trend-key ${topic.theme === selectedTopic ? 'selected' : ''}`} aria-pressed={topic.theme === selectedTopic} onClick={() => { setSelectedTopic(topic.theme === selectedTopic ? null : topic.theme); setSelectedPoint(null); }} key={topic.theme}><i style={{ background: `hsl(${165 + index * 32} 54% 42%)` }} />{short(topic.theme, 24)}</button>)}</div>
    <div className="topic-trend-grid">{dates.map((date) => { const total = selected.reduce((sum, topic) => sum + (topic.date_counts?.[date] || 0), 0); return <div className={`topic-trend-day ${activeDate === date ? 'active' : ''}`} key={date}><span>{date.slice(5)}</span><div className="topic-trend-stack" aria-label={`${date}: ${total} topic reviews`}>{selected.map((topic, index) => { const count = topic.date_counts?.[date] || 0; const isActive = activePoint?.theme === topic.theme && activeDate === date; return <button className={`topic-trend-segment ${isActive ? 'active' : ''}`} aria-label={`${topic.theme}, ${date}: ${count} reviews`} onClick={(event) => { const point = pointFromEvent(topic, date, event); setSelectedTopic(topic.theme); setSelectedPoint(point); }} onMouseEnter={(event) => setHoveredPoint(pointFromEvent(topic, date, event))} onMouseLeave={() => setHoveredPoint(null)} key={topic.theme} style={{ height: `${Math.max(0, (count / max) * 100)}%`, background: `hsl(${165 + index * 32} 54% 42%)`, opacity: selectedTopic && topic.theme !== selectedTopic ? .18 : .86 }} />; })}</div></div>; })}</div>
    {activeTopic && activeDate && <div className="topic-trend-tooltip" aria-live="polite" style={{ left: `${activePoint.left}%`, top: `${activePoint.top}%` }}><strong>{short(activeTopic.theme, 30)}</strong><span>{activeDate}</span><span><b>{activeTopic.date_counts?.[activeDate] || 0}</b> reviews</span></div>}
  </div>;
}
function ComparisonSentiment({ listings }) { return <div className="sentiment-volume comparison-sentiment">{listings.map((item) => <div className="comparison-sentiment-row" key={item.listing_id}><span>{short(item.listing_title, 26)}</span><div className="sentiment-stack"><i className="positive" style={{ width: `${item.positive_sentiment_percent}%` }} /><i className="neutral" style={{ width: `${item.neutral_sentiment_percent}%` }} /><i className="negative" style={{ width: `${item.negative_sentiment_percent}%` }} /></div><strong>{item.reviews}</strong></div>)}</div>; }
function PhraseList({ phrases }) {
  const visible = phrases.filter((phrase) => Number(phrase.mentions || 0) > 10);
  const [selectedPhrase, setSelectedPhrase] = useState(null);
  const [hoveredPhrase, setHoveredPhrase] = useState(null);
  const maxMentions = Math.max(1, ...visible.map((phrase) => phrase.mentions || 0));
  const activePhrase = hoveredPhrase || selectedPhrase;
  if (!visible.length) return <div className="empty-chart">No phrases mentioned more than 10 times yet.</div>;
  return <div className="phrase-cloud" aria-label="Frequent customer language">
    {visible.map((phrase) => {
      const size = 12 + ((phrase.mentions || 0) / maxMentions) * 22;
      return <button type="button"
        className={`phrase-word ${sentimentClass(phrase.average_sentiment)} ${activePhrase?.phrase === phrase.phrase ? 'active' : ''}`}
        key={phrase.phrase}
        style={{ fontSize: `${size}px` }}
        aria-pressed={selectedPhrase?.phrase === phrase.phrase}
        onClick={() => setSelectedPhrase((current) => current?.phrase === phrase.phrase ? null : phrase)}
        onMouseEnter={() => setHoveredPhrase(phrase)} onMouseLeave={() => setHoveredPhrase(null)}
      >{phrase.phrase}</button>;
    })}
    <div className="phrase-detail" aria-live="polite">{activePhrase ? <><strong>{activePhrase.phrase}</strong><span>{activePhrase.mentions} mentions · {formatScore(activePhrase.average_sentiment)} sentiment</span></> : 'Hover or select a word to inspect it.'}</div>
  </div>;
}
function ProductPhrases({ products }) { return <div className="product-phrases">{products.map((product) => <div className="product-phrase" key={product.listing_id}><h4>{short(product.listing_title, 28)}</h4><PhraseList phrases={product.key_phrases || []} /></div>)}</div>; }
function MetricsTable({ listings }) { return <div className="table-wrap"><table><thead><tr><th>Listing</th><th>Satisfaction</th><th>Reviews</th><th>Stars</th><th>Positive</th><th>Negative</th><th>Mismatch</th><th>Topics</th></tr></thead><tbody>{listings.map((item) => <tr key={item.listing_id}><th><span className="rank-chip">#{item.rank}</span>{short(item.listing_title, 32)}</th><td><strong>{item.satisfaction_score}</strong>/100</td><td>{item.reviews}</td><td>{item.average_star_rating ? `${item.average_star_rating}/5` : '-'}</td><td className="green-text">{item.positive_sentiment_percent}%</td><td className="coral-text">{item.negative_sentiment_percent}%</td><td>{item.rating_text_mismatch_percent}%</td><td>{item.topic_count}</td></tr>)}</tbody></table></div>; }
function TopicHeatmap({ data }) { const max = Math.max(1, ...(data?.products || []).flatMap((product) => product.values)); return <div className="heatmap">{data?.topics?.map((topic, index) => <div className="heatmap-col" key={topic}><div className="heatmap-label">{short(topic, 18)}</div>{data.products.map((product) => { const value = product.values[index] || 0; return <div className="heat-cell" title={`${product.listing_title}: ${value} reviews`} key={product.listing_title} style={{ background: `rgba(27,119,116,${0.07 + value / max * 0.8})`, color: value / max > .5 ? '#fff' : 'var(--ink)' }}>{value}</div>; })}</div>)}</div>; }
function TopicMap({ map }) {
  const points = map?.points || [];
  const centroids = map?.centroids || [];
  const normalizedCentroids = Object.values(centroids.reduce((groups, centroid) => {
    const label = normalizeTopicLabel(centroid.label);
    const weight = Number(centroid.size || 1);
    const group = groups[label] || { t: label, label, x: 0, y: 0, sentiment: 0, size: 0 };
    group.x += Number(centroid.x || 0) * weight;
    group.y += Number(centroid.y || 0) * weight;
    group.sentiment += Number(centroid.sentiment || 0) * weight;
    group.size += weight;
    groups[label] = group;
    return groups;
  }, {})).map((centroid) => ({ ...centroid, x: centroid.x / centroid.size, y: centroid.y / centroid.size, sentiment: centroid.sentiment / centroid.size }));
  const [selectedCentroid, setSelectedCentroid] = useState(null);
  const [hoveredCentroid, setHoveredCentroid] = useState(null);
  const all = [...points, ...normalizedCentroids];
  if (!all.length) return <div className="empty-chart">No topic map available yet.</div>;
  const minX = Math.min(...all.map((point) => point.x));
  const maxX = Math.max(...all.map((point) => point.x));
  const minY = Math.min(...all.map((point) => point.y));
  const maxY = Math.max(...all.map((point) => point.y));
  const maxSize = Math.max(1, ...normalizedCentroids.map((centroid) => centroid.size || 0));
  const x = (value) => 8 + ((value - minX) / Math.max(maxX - minX, .001)) * 84;
  const y = (value) => 88 - ((value - minY) / Math.max(maxY - minY, .001)) * 76;
  const topicColors = ['#f1641e', '#4f3a31', '#8b4f8e', '#357960', '#bd7c1c', '#356f8a', '#b94769', '#6c5a9a'];
  const activeCentroid = hoveredCentroid || selectedCentroid;
  return <div className="topic-map">
    {points.map((point, index) => <span className="map-point" style={{ left: `${x(point.x)}%`, top: `${y(point.y)}%` }} key={`${point.t}-${index}`} />)}
    {normalizedCentroids.map((centroid, index) => {
      const size = 24 + ((centroid.size || 0) / maxSize) * 42;
      return <button type="button" className={`map-topic ${activeCentroid?.t === centroid.t ? 'active' : ''}`} style={{ left: `${x(centroid.x)}%`, top: `${y(centroid.y)}%`, width: `${size}px`, height: `${size}px`, background: topicColors[index % topicColors.length] }} aria-label={`${centroid.label}: ${centroid.size} sentences, sentiment ${formatScore(centroid.sentiment)}`} onClick={() => setSelectedCentroid((current) => current?.t === centroid.t ? null : centroid)} onMouseEnter={() => setHoveredCentroid(centroid)} onMouseLeave={() => setHoveredCentroid(null)} key={centroid.t} />;
    })}
    {activeCentroid && <div className={`map-tooltip ${y(activeCentroid.y) < 24 ? 'lower' : ''}`} aria-live="polite" style={{ left: `${x(activeCentroid.x)}%`, top: `${y(activeCentroid.y)}%` }}><strong>{short(activeCentroid.label, 32)}</strong><span>{activeCentroid.size} sentences · {formatScore(activeCentroid.sentiment)} sentiment</span></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
