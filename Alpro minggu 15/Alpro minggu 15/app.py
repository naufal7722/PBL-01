from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


app = Flask(__name__)


# KONFIGURASI MYSQL

app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'manajemen_keuangan'

mysql = MySQL(app)

app.secret_key = "secretkey"
@app.context_processor
def inject_now():
    return {
        'now': datetime.now()
    }


# LOGIN

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, password FROM users WHERE username=%s",
            (username,)
        )
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            return redirect(url_for('index'))

        flash('Username atau password salah')

    return render_template('auth/login.html')



# REGISTER

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s,%s)",
            (username, password)
        )
        mysql.connection.commit()
        cur.close()

        flash('Registrasi berhasil, silakan login')
        return redirect(url_for('login'))

    return render_template('auth/register.html')



# LOGOUT

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))



# DASHBOARD
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    bulan = datetime.now().month
    tahun = datetime.now().year

    cur = mysql.connection.cursor()

    # =====================
    # TOTAL MASUK
    # =====================
    cur.execute("""
        SELECT COALESCE(SUM(nominal),0)
        FROM transaksi
        WHERE user_id=%s AND jenis='masuk'
        AND MONTH(tanggal)=%s AND YEAR(tanggal)=%s
    """, (session['user_id'], bulan, tahun))
    total_masuk = cur.fetchone()[0]

    # =====================
    # TOTAL KELUAR
    # =====================
    cur.execute("""
        SELECT COALESCE(SUM(nominal),0)
        FROM transaksi
        WHERE user_id=%s AND jenis='keluar'
        AND MONTH(tanggal)=%s AND YEAR(tanggal)=%s
    """, (session['user_id'], bulan, tahun))
    total_keluar = cur.fetchone()[0]

    saldo = total_masuk - total_keluar

    # =====================
    # TRANSAKSI TERAKHIR
    # =====================
    cur.execute("""
        SELECT t.id, t.tanggal, t.jenis, k.nama_kategori, t.nominal, t.keterangan
        FROM transaksi t
        JOIN kategori k ON t.kategori_id = k.id
        WHERE t.user_id=%s
        ORDER BY t.tanggal DESC
        LIMIT 5
    """, (session['user_id'],))
    transaksi = cur.fetchall()

    # =====================
    # ANGGARAN PER KATEGORI
    # =====================
    cur.execute("""
        SELECT
            k.nama_kategori,
            IFNULL(SUM(a.nominal), 0) AS total_anggaran,
            IFNULL(SUM(t.nominal), 0) AS total_keluar
        FROM kategori k
        LEFT JOIN anggaran a
            ON a.kategori_id = k.id
            AND a.user_id = %s
            AND a.bulan = %s
            AND a.tahun = %s
        LEFT JOIN transaksi t
            ON t.kategori_id = k.id
            AND t.user_id = %s
            AND t.jenis = 'keluar'
            AND MONTH(t.tanggal) = %s
            AND YEAR(t.tanggal) = %s
        WHERE k.user_id = %s
        GROUP BY k.id
    """, (
        session['user_id'], bulan, tahun,
        session['user_id'], bulan, tahun,
        session['user_id']
    ))

    anggaran_kategori = cur.fetchall()
    cur.close()

    return render_template(
        'index.html',
        total_masuk=total_masuk,
        total_keluar=total_keluar,
        saldo=saldo,
        transaksi=transaksi,
        anggaran_kategori=anggaran_kategori,
        active='dashboard'
    )


# LIST TRANSAKSI

@app.route('/transaksi')
def data_transaksi():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            t.id,
            t.tanggal,
            t.jenis,
            k.nama_kategori,
            t.nominal,
            t.keterangan
        FROM transaksi t
        JOIN kategori k ON t.kategori_id = k.id
        WHERE t.user_id = %s
        ORDER BY t.tanggal DESC
    """, (session['user_id'],))
    data = cur.fetchall()
    cur.close()

    return render_template(
        'transaksi/data-transaksi.html', 
        transaksi=data,
        active='transaksi')



# TAMBAH TRANSAKSI
@app.route('/transaksi/tambah')
def tambah_transaksi():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, nama_kategori FROM kategori")
    kategori = cur.fetchall()
    cur.close()

    return render_template(
        'transaksi/tambah-transaksi.html',
        kategori=kategori
    )


@app.route('/transaksi/insert', methods=['POST'])
def insert_transaksi():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tanggal = request.form['tanggal']
    jenis = request.form['jenis']
    kategori_id = request.form['kategori_id']
    nominal = request.form['nominal']
    keterangan = request.form['keterangan']

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO transaksi 
        (user_id, tanggal, jenis, kategori_id, nominal, keterangan)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        session['user_id'],
        tanggal,
        jenis,
        kategori_id,
        nominal,
        keterangan
    ))
    mysql.connection.commit()
    cur.close()

    flash('Transaksi berhasil ditambahkan')
    return redirect(url_for('data_transaksi'))


# EDIT TRANSAKSI
@app.route('/transaksi/edit/<int:id>')
def edit_transaksi(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # ambil transaksi
    cur.execute("""
        SELECT id, user_id, tanggal, jenis, kategori_id, nominal, keterangan
        FROM transaksi
        WHERE id=%s AND user_id=%s
    """, (id, session['user_id']))
    transaksi = cur.fetchone()

    # ambil SEMUA kategori
    cur.execute("""
        SELECT id, nama_kategori
        FROM kategori
        WHERE user_id=%s
    """, (session['user_id'],))
    kategori = cur.fetchall()

    cur.close()

    return render_template(
        'transaksi/edit-transaksi.html',
        transaksi=transaksi,
        kategori=kategori
    )



@app.route('/transaksi/update/<int:id>', methods=['POST'])
def update_transaksi(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    tanggal = request.form['tanggal']
    jenis = request.form['jenis']
    kategori_id = request.form['kategori_id']
    nominal = request.form['nominal']
    keterangan = request.form['keterangan']

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE transaksi
        SET tanggal=%s, jenis=%s, kategori_id=%s, nominal=%s, keterangan=%s
        WHERE id=%s AND user_id=%s
    """, (
        tanggal,
        jenis,
        kategori_id,
        nominal,
        keterangan,
        id,
        session['user_id']
    ))
    mysql.connection.commit()
    cur.close()

    flash('Transaksi berhasil diubah')
    return redirect(url_for('data_transaksi'))


# HAPUS TRANSAKSI
@app.route('/transaksi/delete/<int:id>')
def delete_transaksi(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute(
        "DELETE FROM transaksi WHERE id=%s AND user_id=%s",
        (id, session['user_id'])
    )
    mysql.connection.commit()
    cur.close()

    flash('Transaksi berhasil dihapus')
    return redirect(url_for('data_transaksi'))

# LIST KATEGORI
@app.route('/kategori')
def data_kategori():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, nama_kategori 
        FROM kategori
        WHERE user_id = %s
        ORDER BY id DESC
    """, (session['user_id'],))
    data = cur.fetchall()
    cur.close()

    return render_template(
        'kategori/data-kategori.html',
        kategori=data,
        active='kategori'
    )

# TAMBAH KATEGORI
@app.route('/kategori/tambah')
def tambah_kategori():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template('kategori/tambah-kategori.html')

@app.route('/kategori/insert', methods=['POST'])
def insert_kategori():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    nama_kategori = request.form['nama_kategori']

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO kategori (user_id, nama_kategori)
        VALUES (%s,%s)
    """, (session['user_id'], nama_kategori))
    mysql.connection.commit()
    cur.close()

    flash('Kategori berhasil ditambahkan')
    return redirect(url_for('data_kategori'))

# EDIT KATEGORI
@app.route('/kategori/edit/<int:id>')
def edit_kategori(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, nama_kategori 
        FROM kategori 
        WHERE id=%s AND user_id=%s
    """, (id, session['user_id']))
    data = cur.fetchone()
    cur.close()

    return render_template(
        'kategori/ubah-kategori.html',
        kategori=data
    )

@app.route('/kategori/update/<int:id>', methods=['POST'])
def update_kategori(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    nama_kategori = request.form['nama_kategori']

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE kategori 
        SET nama_kategori=%s 
        WHERE id=%s AND user_id=%s
    """, (nama_kategori, id, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash('Kategori berhasil diubah')
    return redirect(url_for('data_kategori'))

# DELETE KATEGORI
@app.route('/kategori/delete/<int:id>')
def delete_kategori(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        DELETE FROM kategori 
        WHERE id=%s AND user_id=%s
    """, (id, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash('Kategori berhasil dihapus')
    return redirect(url_for('data_kategori'))

# LIST ANGGARAN
@app.route('/anggaran')
def data_anggaran():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            a.id,
            k.nama_kategori,
            a.bulan,
            a.tahun,
            a.nominal
        FROM anggaran a
        JOIN kategori k ON a.kategori_id = k.id
        WHERE a.user_id = %s
        ORDER BY a.bulan DESC
    """, (session['user_id'],))
    data = cur.fetchall()
    cur.close()

    return render_template(
        'anggaran/data-anggaran.html',
        anggaran=data,
        active='anggaran'
    )


# TAMBAH ANGGARAN
@app.route('/anggaran/tambah')
def tambah_anggaran():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, nama_kategori 
        FROM kategori 
        WHERE user_id=%s
    """, (session['user_id'],))
    kategori = cur.fetchall()
    cur.close()

    return render_template(
        'anggaran/tambah-anggaran.html',
        kategori=kategori
    )

@app.route('/anggaran/insert', methods=['POST'])
def insert_anggaran():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    kategori_id = request.form['kategori_id']
    bulan = request.form['bulan']
    nominal = request.form['nominal']
    tahun = request.form['tahun']

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO anggaran 
        (user_id, kategori_id, bulan, nominal, tahun)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        session['user_id'],
        kategori_id,
        bulan,
        nominal,
        tahun
    ))
    mysql.connection.commit()
    cur.close()

    flash('Anggaran berhasil ditambahkan')
    return redirect(url_for('data_anggaran'))


# EDIT ANGGARAN
@app.route('/anggaran/edit/<int:id>')
def edit_anggaran(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT a.id, a.kategori_id, a.bulan, a.tahun, a.nominal, k.nama_kategori
        FROM anggaran a
        JOIN kategori k ON a.kategori_id = k.id
        WHERE a.id=%s AND a.user_id=%s
    """, (id, session['user_id']))
    anggaran = cur.fetchone()

    cur.execute("SELECT id, nama_kategori FROM kategori WHERE user_id=%s", (session['user_id'],))
    kategori = cur.fetchall()
    cur.close()

    return render_template(
        'anggaran/ubah-anggaran.html',
        anggaran=anggaran,
        kategori=kategori
    )

# UPDATE ANGGARAN
@app.route('/anggaran/update/<int:id>', methods=['POST'])
def update_anggaran(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    kategori_id = request.form['kategori_id']
    bulan = request.form['bulan']
    nominal = request.form['nominal']
    tahun = request.form['tahun']

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE anggaran
        SET kategori_id=%s, bulan=%s, tahun=%s, nominal=%s
        WHERE id=%s AND user_id=%s
    """, (kategori_id, bulan, tahun, nominal, id, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash('Anggaran berhasil diubah')
    return redirect(url_for('data_anggaran'))


# DELETE ANGGARAN
@app.route('/anggaran/delete/<int:id>')
def delete_anggaran(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        DELETE FROM anggaran 
        WHERE id=%s AND user_id=%s
    """, (id, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash('Anggaran berhasil dihapus')
    return redirect(url_for('data_anggaran'))


# RUN APP
if __name__ == "__main__":
    app.run(debug=True, port=9999)