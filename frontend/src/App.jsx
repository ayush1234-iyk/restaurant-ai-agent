import { useEffect, useRef, useState } from 'react'
import './App.css'

const API = 'https://restaurant-ai-agent-1-fskp.onrender.com';

const FOOD_IMAGES = [
  {
    keywords: ['pizza'],
    image: 'https://images.unsplash.com/photo-1579751626657-72bc17010498?auto=format&fit=crop&w=900&q=85',
    emoji: '🍕',
  },
  {
    keywords: ['burger'],
    image: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=900&q=85',
    emoji: '🍔',
  },
  {
    keywords: ['pasta', 'noodle', 'macaroni', 'spaghetti'],
    image: 'https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=900&q=85',
    emoji: '🍝',
  },
  {
    keywords: ['coffee', 'cold coffee', 'espresso'],
    image: 'https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=900&q=85',
    emoji: '☕',
  },
  {
    keywords: ['shake', 'smoothie', 'juice', 'drink', 'lemonade'],
    image: 'https://images.unsplash.com/photo-1546173159-315724a31696?auto=format&fit=crop&w=900&q=85',
    emoji: '🥤',
  },
  {
    keywords: ['fries', 'french fries', 'potato'],
    image: 'https://images.unsplash.com/photo-1573080496219-bb080dd4f877?auto=format&fit=crop&w=900&q=85',
    emoji: '🍟',
  },
  {
    keywords: ['brownie', 'cake', 'chocolate', 'dessert', 'ice cream'],
    image: 'https://images.unsplash.com/photo-1606313564200-e75d5e30476c?auto=format&fit=crop&w=900&q=85',
    emoji: '🍰',
  },
  {
    keywords: ['sandwich', 'sub'],
    image: 'https://images.unsplash.com/photo-1528735602780-2552fd46c7af?auto=format&fit=crop&w=900&q=85',
    emoji: '🥪',
  },
  {
    keywords: ['momos', 'dumpling'],
    image: 'https://images.unsplash.com/photo-1563245372-f21724e3856d?auto=format&fit=crop&w=900&q=85',
    emoji: '🥟',
  },
  {
    keywords: ['salad'],
    image: 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=900&q=85',
    emoji: '🥗',
  },
]

function getFood(item) {
  const name = (item.dish_name || '').toLowerCase()

  return (
    FOOD_IMAGES.find((food) =>
      food.keywords.some((keyword) => name.includes(keyword))
    ) || {
      image:
        'https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=900&q=85',
      emoji: '🍽️',
    }
  )
}

export default function App() {
  const [menu, setMenu] = useState([])

  const [customer, setCustomer] = useState(
    () => localStorage.getItem('foodie_customer') || ''
  )

  const [nameInput, setNameInput] = useState('')
  const [message, setMessage] = useState('')

  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: "Hey there! 👋 I'm your FoodieAI assistant. What are you craving today?",
    },
  ])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [menuLoading, setMenuLoading] = useState(true)
  const [activeCategory, setActiveCategory] = useState('All')
  const [search, setSearch] = useState('')

  // Reference sirf chat messages ke scroll container ke liye hai.
  const messagesContainerRef = useRef(null)

  const [sessionId] = useState(() => {
    let id = localStorage.getItem('foodie_session')

    if (!id) {
      id = `session_${Date.now()}`
      localStorage.setItem('foodie_session', id)
    }

    return id
  })


async function loadMenu() {
  setMenuLoading(true)

  try {
    const response = await fetch(`${API}/menu`)

    if (!response.ok) {
      const details = await response.text()

      throw new Error(
        `Menu API returned ${response.status}: ${details}`
      )
    }

    const data = await response.json()

    if (!Array.isArray(data)) {
      throw new Error('Menu API did not return a list of dishes.')
    }

    setMenu(data)
    setError('')
  } catch (err) {
    console.error('Menu loading error:', err)

    setError(
      err instanceof Error
        ? err.message
        : 'Unknown error while loading the menu.'
    )
  } finally {
    setMenuLoading(false)
  }
}

  useEffect(() => {
    loadMenu()
  }, [])

  // Scroll sirf chat ke andar hoga, poora page nahi.
  useEffect(() => {
    const container = messagesContainerRef.current

    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [messages, loading])


async function sendMessage(text = message) {
  const clean = text.trim()

  if (!clean || loading || !customer.trim()) {
    return
  }

  setMessages((old) => [
    ...old,
    { role: 'user', text: clean },
  ])

  setMessage('')
  setLoading(true)

  try {
    const response = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        customer_name: customer.trim(),
        message: clean,
        session_id: sessionId,
      }),
    })

    const responseText = await response.text()

    let data

    try {
      data = JSON.parse(responseText)
    } catch {
      throw new Error(
        `Invalid server response (HTTP ${response.status}).`
      )
    }

    if (!response.ok) {
      throw new Error(
        data.detail || `Request failed (${response.status}).`
      )
    }

    setMessages((old) => [
      ...old,
      {
        role: 'assistant',
        text: data.reply || 'I received your message!',
      },
    ])

    if (['complete', 'cancelled'].includes(data.status)) {
      await loadMenu()
    }
  } catch (err) {
    console.error('sendMessage failed:', err)

    setMessages((old) => [
      ...old,
      {
        role: 'assistant',
        text: `Request failed: ${
          err instanceof Error ? err.message : 'Unknown error'
        }`,
      },
    ])
  } finally {
    setLoading(false)
  }
}


  function saveName(event) {
    event.preventDefault()

    const clean = nameInput.trim()

    if (!clean) {
      return
    }

    localStorage.setItem('foodie_customer', clean)
    setCustomer(clean)

    setMessages((old) => [
      ...old,
      {
        role: 'assistant',
        text: `Welcome, ${clean}! Tell me what you'd like to order.`,
      },
    ])

    setNameInput('')
  }

  function startOrdering(item) {
    if (!customer.trim()) {
      document.getElementById('customer-name')?.focus()
      return
    }

    sendMessage(`I want 1 ${item.dish_name}`)
  }

  const availableCount = menu.filter(
    (item) => Number(item.stock) > 0
  ).length

  const categories = [
    'All',
    'Pizza',
    'Burger',
    'Pasta',
    'Drinks',
    'Desserts',
  ]

  const filteredMenu = menu.filter((item) => {
    const name = (item.dish_name || '').toLowerCase()
    const matchesSearch = name.includes(search.toLowerCase())

    if (!matchesSearch) {
      return false
    }

    if (activeCategory === 'All') {
      return true
    }

    if (activeCategory === 'Drinks') {
      return /drink|coffee|juice|shake|beverage|lemonade|tea/i.test(name)
    }

    if (activeCategory === 'Desserts') {
      return /cake|brownie|dessert|ice cream|sweet|gulab|pastry/i.test(name)
    }

    return name.includes(activeCategory.toLowerCase())
  })

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" aria-label="FoodieAI home">
          <span
            className="brand-icon chef-mascot"
            aria-label="Cute animated chef"
          >
            👨‍🍳
          </span>

          <span>
            foodie<span className="brand-accent">AI</span>
          </span>

          <span className="brand-sparkle">✦</span>
        </a>

        <div className="side-label">YOUR WORKSPACE</div>

        <button
          className="side-link active"
          onClick={() =>
            window.scrollTo({
              top: 0,
              behavior: 'smooth',
            })
          }
        >
          <span className="nav-icon">✧</span>
          <span>AI Assistant</span>
        </button>

        <button
          className="side-link"
          onClick={() => sendMessage('Show my order history')}
        >
          <span className="nav-icon">◷</span>
          <span>Order history</span>
        </button>

        <button
          className="side-link"
          onClick={() => sendMessage('Track my order')}
        >
          <span className="nav-icon">♧</span>
          <span>Track an order</span>
        </button>

        <div className="sidebar-art">
          <div className="sidebar-art-orbit orbit-one" />
          <div className="sidebar-art-orbit orbit-two" />
          <span>✳</span>
          <p>
            Good food.
            <br />
            Better mood.
          </p>
        </div>

        <div className="sidebar-bottom">
          <span className="online-dot" />

          <div>
            <strong>AI system</strong>
            <small>
              {error ? 'Connection needed' : 'Ready to serve'}
            </small>
          </div>

          <span
            className={`status-pill ${error ? 'status-offline' : ''}`}
          >
            {error ? 'OFFLINE' : 'LIVE'}
          </span>
        </div>
      </aside>

      <main className="main-area" id="home">
        <header className="topbar">
          <div>
            <div className="eyebrow">
              YOUR PERSONAL FOOD ASSISTANT
            </div>

            <h1 className="mood-heading">
              Good food. <span>Good mood.</span>

              <span
                className="mood-mascot"
                aria-label="Steaming ramen bowl"
              >
                <span className="mood-spark spark-left">✦</span>
                <span className="mood-steam">〰</span>
                <span className="mood-bowl">🍜</span>
                <span className="mood-spark spark-right">✧</span>
              </span>
            </h1>

            <p className="topbar-subtitle">
              A little comfort, one delicious bite at a time.
            </p>
          </div>

          <div className="profile">
            <div className="profile-avatar">
              {customer ? customer[0].toUpperCase() : 'G'}
            </div>

            <div className="profile-copy">
              <strong>{customer || 'Guest user'}</strong>
              <small>
                Food lover <span>✦</span>
              </small>
            </div>

            <span className="profile-chevron">⌄</span>
          </div>
        </header>

        <section className="hero">
          <div className="hero-image" />
          <div className="hero-shade" />

          <div className="hero-copy">
            <span className="hero-tag">
              <span>✦</span> GOOD TASTE. SMARTER SERVICE.
            </span>

            <h2>
              Cravings?
              <br />
              We've got <span>you.</span>
            </h2>

            <p>
              Restaurant-quality comfort, delivered through your personal AI
              food assistant. Find your favourite, place your order, and enjoy
              the moment.
            </p>

            <button
              className="primary-button"
              onClick={() => {
                document
                  .getElementById('menu-section')
                  ?.scrollIntoView({
                    behavior: 'smooth',
                  })
              }}
            >
              Explore the menu <span>↗</span>
            </button>
          </div>

          <div className="hero-art-label">
            <span className="hero-label-icon">✦</span>
            <span>
              <strong>Made fresh.</strong>
              <small>Served with love.</small>
            </span>
          </div>

          <div className="hero-bottom-tags">
            <span>✧ Fresh ingredients</span>
            <span>✦ AI powered</span>
            <span>✓ Made for you</span>
          </div>
        </section>

        <section className="stats-row">
          <div className="stat-card">
            <span className="stat-icon orange-icon">♨</span>

            <div>
              <small>MENU ITEMS</small>
              <strong>{menu.length}</strong>
              <span className="stat-caption">
                Made for your cravings
              </span>
            </div>
          </div>

          <div className="stat-card">
            <span className="stat-icon green-icon">✓</span>

            <div>
              <small>AVAILABLE NOW</small>
              <strong>{availableCount}</strong>
              <span className="stat-caption">
                Ready to be ordered
              </span>
            </div>
          </div>

          <div className="stat-card">
            <span className="stat-icon purple-icon">✦</span>

            <div>
              <small>YOUR AI CHEF</small>
              <strong className="ready-text">Ready to help</strong>
              <span className="stat-caption">
                Ask anything, anytime
              </span>
            </div>

            <span className="stat-live">
              <span /> LIVE
            </span>
          </div>
        </section>

        <div className="content-grid">
          <section className="panel menu-panel" id="menu-section">
            <div className="section-heading">
              <div>
                <div className="eyebrow">
                  A LITTLE SOMETHING DELICIOUS
                </div>

                <h2>
                  Find your <span>favourite.</span>
                </h2>

                <p className="section-subtitle">
                  Fresh picks for whatever you're craving.
                </p>
              </div>

              <button
                className="text-button"
                onClick={loadMenu}
                disabled={menuLoading}
              >
                {menuLoading ? 'Loading…' : 'Refresh ↻'}
              </button>
            </div>

            <div className="menu-toolbar">
              <div className="category-list">
                {categories.map((category) => (
                  <button
                    key={category}
                    className={`category-button ${
                      activeCategory === category ? 'selected' : ''
                    }`}
                    onClick={() => setActiveCategory(category)}
                  >
                    {category === 'All' && <span>✦</span>}
                    {category}
                  </button>
                ))}
              </div>

              <label className="menu-search">
                <span>⌕</span>

                <input
                  type="search"
                  placeholder="Find a dish..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  aria-label="Search menu"
                />
              </label>
            </div>

            {error && (
              <div className="error-banner">
                <span>!</span>

                <div>
                  <strong>
                    We couldn't connect to your kitchen.
                  </strong>
                  <p>{error}</p>
                </div>

                <button onClick={loadMenu}>Retry</button>
              </div>
            )}

            <div className="menu-grid">
              {filteredMenu.map((item, index) => {
                const food = getFood(item)
                const stock = Number(item.stock) || 0

                return (
                  <article
                    className="food-card"
                    key={item.id ?? item.dish_name}
                  >
                    <div className={`food-picture food-picture-${index % 4}`}>
                      <img
                        src={food.image}
                        alt={item.dish_name}
                        loading={index < 4 ? 'eager' : 'lazy'}
                        onError={(event) => {
                          event.currentTarget.style.display = 'none'

                          event.currentTarget.parentElement.classList.add(
                            'image-failed'
                          )
                        }}
                      />

                      <span
                        className="image-fallback"
                        aria-hidden="true"
                      >
                        {food.emoji}
                      </span>

                      <span
                        className={`stock-badge ${
                          stock <= 0 ? 'sold-out' : ''
                        }`}
                      >
                        {stock > 0 ? `${stock} left` : 'Sold out'}
                      </span>

                      <span className="food-image-overlay" />
                    </div>

                    <div className="food-info">
                      <div className="food-name-row">
                        <h3 title={item.dish_name}>
                          {item.dish_name}
                        </h3>

                        <span className="food-rating">✦</span>
                      </div>

                      <p className="food-description">
                        {stock > 0
                          ? 'A delicious choice, made for you.'
                          : 'Currently unavailable'}
                      </p>

                      <div className="food-bottom">
                        <div>
                          <small>PRICE</small>
                          <strong>
                            ₹{Number(item.price).toFixed(0)}
                          </strong>
                        </div>

                        <button
                          className="add-button"
                          disabled={stock <= 0}
                          onClick={() => startOrdering(item)}
                          title={
                            stock > 0
                              ? `Order ${item.dish_name}`
                              : 'Currently unavailable'
                          }
                          aria-label={`Order ${item.dish_name}`}
                        >
                          +
                        </button>
                      </div>
                    </div>
                  </article>
                )
              })}

              {!menuLoading && !error && filteredMenu.length === 0 && (
                <div className="empty-menu">
                  <span>🍽️</span>
                  <h3>No dishes found</h3>
                  <p>
                    Try another search or choose a different category.
                  </p>

                  <button
                    onClick={() => {
                      setSearch('')
                      setActiveCategory('All')
                    }}
                  >
                    Show all dishes
                  </button>
                </div>
              )}

              {menuLoading && !menu.length && (
                <div className="empty-menu">
                  <span className="loading-orbit">✦</span>
                  <h3>Setting the table...</h3>
                  <p>Getting the menu ready for you.</p>
                </div>
              )}
            </div>

            <div className="menu-footnote">
              <span>✦</span> Good food, good mood. Always.

              <button onClick={() => sendMessage('Show me the menu')}>
                Ask the AI chef ↗
              </button>
            </div>
          </section>

          <section className="panel chat-panel">
            <div className="chat-heading">
              <div className="bot-avatar chef-logo">👨‍🍳</div>

              <div className="chat-title">
                <h2>Your AI chef</h2>
                <p>
                  <span className="online-dot" /> Here to make life delicious
                </p>
              </div>

              <span className="chat-live">LIVE</span>
            </div>

            {!customer && (
              <form className="name-form" onSubmit={saveName}>
                <label htmlFor="customer-name">
                  Let's start with your name
                </label>

                <p>Your personal food assistant is ready.</p>

                <div>
                  <input
                    id="customer-name"
                    value={nameInput}
                    onChange={(event) => setNameInput(event.target.value)}
                    placeholder="What should we call you?"
                    autoComplete="given-name"
                    required
                  />

                  <button type="submit">Let's go ↗</button>
                </div>
              </form>
            )}

            <div className="chat-intro">
              <span className="chat-intro-icon">✧</span>
              <span>
                Tell me what you're craving. I'll take it from here.
              </span>
            </div>

            {/* Corrected: scroll container has its own ref */}
            <div
              className="messages"
              aria-live="polite"
              ref={messagesContainerRef}
            >
              {messages.map((item, index) => (
                <div
                  className={`message-row ${item.role}`}
                  key={index}
                >
                  {item.role === 'assistant' && (
                    <div className="message-avatar chef-message-logo">
                      👨‍🍳
                    </div>
                  )}

                  <div className="message-content">
                    <span className="message-sender">
                      {item.role === 'assistant' ? 'FOODIE AI' : 'YOU'}
                    </span>

                    <div className="message-bubble">
                      {item.text}
                    </div>
                  </div>
                </div>
              ))}

              {loading && (
                <div className="typing-row">
                  <div className="message-avatar">✦</div>

                  <div className="typing">
                    Preparing your response <span>•••</span>
                  </div>
                </div>
              )}
            </div>

            <div className="suggestions">
              <span className="suggestions-label">QUICK ACTIONS</span>

              <div className="suggestion-buttons">
                <button onClick={() => sendMessage('Show me the menu')}>
                  ♧ &nbsp; View menu
                </button>

                <button onClick={() => sendMessage('Track my order')}>
                  ↗ &nbsp; Track order
                </button>

                <button
                  onClick={() => sendMessage('Show my order history')}
                >
                  ◷ &nbsp; My orders
                </button>
              </div>
            </div>

            <form
              className="chat-input-row"
              onSubmit={(event) => {
                event.preventDefault()
                sendMessage()
              }}
            >
              <input
                id="chat-input"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={
                  customer
                    ? 'Tell me what you are craving...'
                    : 'Enter your name above first...'
                }
                disabled={!customer || loading}
                aria-label="Message your AI chef"
              />

              <button
                type="submit"
                disabled={!customer || loading || !message.trim()}
                aria-label="Send message"
              >
                ↗
              </button>
            </form>

            <p className="chat-disclaimer">
              <span>✦</span> AI-powered ordering · Check order details before
              confirming
            </p>
          </section>
        </div>

        <footer className="footer">
          <span>
            © 2026 <strong>foodie<span>AI</span></strong>. Made for food lovers.
          </span>

          <span>
            Crafted with <b>♥</b> and a little bit of AI.
          </span>
        </footer>
      </main>
    </div>
  )
}


