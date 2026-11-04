const workflow = [
  { number: "01", title: "Bring a long video", body: "A conversation, a recording, a moment that deserves a second life." },
  { number: "02", title: "Find the thread", body: "Speech and context help surface complete thoughts, with timestamps you can follow." },
  { number: "03", title: "Make it yours", body: "Shape the cut, refine captions, and approve every frame before it leaves your hands." },
];

const features = [
  { index: "A", title: "The thought, intact.", body: "Highlights are meant to carry a beginning, a turn, and a landing. You choose what feels true to the conversation." },
  { index: "B", title: "Every cut has a reason.", body: "See the words, time range, and signals behind a suggestion. Nothing is published for you." },
  { index: "C", title: "Ready for the frame.", body: "A considered vertical composition, readable captions, and room for platform overlays." },
];

function Wordmark() {
  return <a className="wordmark" href="#top" aria-label="ClipForge AI home"><span className="wordmark-mark">C<span>·</span></span><span>CLIPFORGE<span className="wordmark-ai"> AI</span></span></a>;
}

export default function Home() {
  return (
    <main id="top">
      <header className="site-header">
        <Wordmark />
        <nav className="primary-nav" aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#features">Why ClipForge</a>
          <a href="#principles">Principles</a>
        </nav>
        <a className="nav-cta" href="/workspace">Open workspace <span aria-hidden="true">↗</span></a>
      </header>

      <section className="hero section-wrap" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow"><span className="eyebrow-line" /> A better way to find the moment</p>
          <h1 id="hero-title">Long stories.<br /><span>Short,</span> with <em>meaning.</em></h1>
          <p className="hero-intro">The best moment is already in there. ClipForge helps you find it, shape it, and share it on your terms.</p>
          <div className="hero-actions">
            <a className="button button-bright" href="/workspace">Start a project <span aria-hidden="true">↗</span></a>
            <a className="text-link" href="#how-it-works"><span className="play-icon" aria-hidden="true">▶</span> See how it works</a>
          </div>
          <div className="hero-note"><span className="note-dot" /> Thoughtful cuts. Creator-approved, always.</div>
        </div>

        <div className="hero-art" aria-label="Illustrative preview of a selected video highlight">
          <div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" />
          <div className="video-card">
            <div className="video-topline"><span>HIGHLIGHT / 03</span><span className="confidence"><i /> COMPLETE THOUGHT</span></div>
            <div className="video-image">
              <div className="image-grid" />
              <div className="portrait portrait-back" /><div className="portrait portrait-front" />
              <div className="video-caption"><span>“The thing that changed was</span><strong>asking a better question.”</strong></div>
              <div className="video-time">08:42 <span>—</span> 09:18</div>
            </div>
            <div className="video-controls"><span className="control-play">▶</span><div className="scrub"><span /></div><span className="control-time">00:12 / 00:36</span><span className="control-expand">↗</span></div>
            <div className="video-meta"><div><span className="meta-label">WHY IT WORKS</span><span className="meta-value">Clear setup · Useful payoff</span></div><span className="draft-tag">DRAFT</span></div>
          </div>
          <div className="art-caption"><span className="caption-star">✳</span><span>One idea, kept intact.</span></div>
          <div className="art-index">01 <span>/</span> 03</div>
        </div>
      </section>

      <div className="ticker" aria-label="Product principles"><div className="ticker-track"><span>FIND THE THREAD</span><i>✳</i><span>KEEP THE CONTEXT</span><i>✳</i><span>YOU MAKE THE CALL</span><i>✳</i><span>FIND THE THREAD</span><i>✳</i><span>KEEP THE CONTEXT</span><i>✳</i><span>YOU MAKE THE CALL</span><i>✳</i></div></div>

      <section className="workflow section-wrap" id="how-it-works">
        <div className="section-heading"><div><p className="eyebrow eyebrow-dark"><span className="eyebrow-line" /> THE WORKFLOW</p><h2>A good story<br />has a <em>shape.</em></h2></div><p className="section-aside">From the first listen to the final frame, you stay close to the story.</p></div>
        <div className="workflow-grid">{workflow.map((item) => <article className="workflow-item" key={item.number}><span className="step-number">{item.number}</span><h3>{item.title}</h3><p>{item.body}</p><span className="step-arrow" aria-hidden="true">↗</span></article>)}</div>
      </section>

      <section className="features" id="features"><div className="section-wrap feature-inner"><div className="feature-heading"><p className="eyebrow"><span className="eyebrow-line" /> MADE FOR THE WAY YOU CREATE</p><h2>Useful moments.<br /><em>Not noise.</em></h2><p>Good editing is a way of listening. We’re building tools that help your story travel without losing what made it worth telling.</p></div><div className="feature-list">{features.map((feature) => <article className="feature-item" key={feature.index}><span className="feature-index">{feature.index}</span><div><h3>{feature.title}</h3><p>{feature.body}</p></div><span className="feature-arrow" aria-hidden="true">↗</span></article>)}</div></div></section>

      <section className="principles section-wrap" id="principles"><div className="principle-mark" aria-hidden="true">✳</div><div className="principle-copy"><p className="eyebrow eyebrow-dark"><span className="eyebrow-line" /> OUR PROMISE</p><h2>Your voice.<br /><em>Your call.</em></h2></div><div className="principle-details"><p>AI can point to a moment. Only you know what it means.</p><ul><li>Suggestions stay editable drafts</li><li>Every clip gets your review</li><li>Your source and your rights matter</li></ul></div></section>

      <section className="closing" id="start"><div className="closing-inner section-wrap"><p className="eyebrow"><span className="eyebrow-line" /> CLIPFORGE AI · IN THE MAKING</p><h2>The next good<br />moment is <em>in there.</em></h2><p>Create a local project, add a video you own or have permission to process, generate a timestamped transcript, and review candidate windows. Quality ranking and clip editing are still in development.</p><a className="button button-dark" href="/workspace">Open workspace <span aria-hidden="true">↗</span></a><span className="closing-spark" aria-hidden="true">✳</span></div></section>

      <footer className="site-footer"><div className="section-wrap footer-inner"><Wordmark /><p>Made for stories worth sharing.</p><span>© 2026 ClipForge AI <span className="footer-divider">·</span> Early concept</span></div></footer>
    </main>
  );
}
